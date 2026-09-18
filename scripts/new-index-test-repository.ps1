param(
    [string]$Destination = 'D:\RepoPilot\test-data\index-fixture'
)

$ErrorActionPreference = 'Stop'
$fixtureRoot = [System.IO.Path]::GetFullPath($Destination)
if (Test-Path -LiteralPath $fixtureRoot) {
    throw "Destination already exists; choose a new directory: $fixtureRoot"
}
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    throw 'Git must be installed and available on PATH.'
}

New-Item -ItemType Directory -Path $fixtureRoot | Out-Null
$utf8 = New-Object System.Text.UTF8Encoding($false)

function Write-FixtureText([string]$RelativePath, [string]$Content) {
    $target = Join-Path $fixtureRoot $RelativePath
    [System.IO.Directory]::CreateDirectory([System.IO.Path]::GetDirectoryName($target)) | Out-Null
    [System.IO.File]::WriteAllText($target, $Content.Replace("`r`n", "`n"), $utf8)
}

function Invoke-FixtureGit {
    & git -C $fixtureRoot @args
    if ($LASTEXITCODE -ne 0) { throw "Git operation failed: $args" }
}

Write-FixtureText 'app.py' @'
def add(a, b):
    return a + b

async def ping():
    return "pong"

class Greeter:
    def greet(self):
        return "hello"
'@
Write-FixtureText 'pkg/helpers.py' @'
@decorate
def decorated():
    return 42
'@
Write-FixtureText 'nested.py' @'
def outer():
    def inner():
        return 1
    return inner()
'@
Write-FixtureText 'constants.py' "ANSWER = 42`n"
Write-FixtureText 'empty.py' ''
Write-FixtureText 'bad/syntax.py' "def broken(:`n    pass`n"
Write-FixtureText 'bad/encoding.py' "# coding: definitely-not-an-encoding`nvalue = 1`n"
[System.IO.File]::WriteAllBytes((Join-Path $fixtureRoot 'bad/null.py'), [byte[]](35, 0, 10))
# Two valid first lines ensure encoding detection succeeds before decoding fails.
[System.IO.File]::WriteAllBytes((Join-Path $fixtureRoot 'bad/decode.py'),
    [byte[]](35, 32, 111, 107, 10, 35, 32, 111, 107, 10, 255, 10))
Write-FixtureText 'bad/large.py' ('#' + ('x' * 1048576))
Write-FixtureText 'README.md' "Index API fixture; intentionally includes invalid Python files.`n"
Write-FixtureText 'ignored.txt' "def not_python(): pass`n"
foreach ($directory in @('.venv', 'venv', 'node_modules', '__pycache__')) {
    Write-FixtureText "$directory/ignored.py" "def excluded(): pass`n"
}
# Keep byte sizes and hashes identical after clone on Windows.
Write-FixtureText '.gitattributes' "* -text`n"
Invoke-FixtureGit init
Invoke-FixtureGit add --force --all
# Identity and signing overrides apply only to this commit, not global Git config.
Invoke-FixtureGit -c user.name=RepoPilot-Test -c user.email=repopilot-test@example.invalid -c commit.gpgsign=false commit -m 'Add index API test fixture'
$dirty = Invoke-FixtureGit status --porcelain=v1 --untracked-files=all
if ($dirty) { throw 'Fixture working tree is not clean.' }
Write-Output "Source path: $fixtureRoot"
Write-Output 'Expected index result: file_count=5, chunk_count=5, skipped_files=5'
