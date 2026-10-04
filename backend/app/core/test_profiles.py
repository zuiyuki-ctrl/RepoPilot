from dataclasses import dataclass

from .exceptions import InvalidRepositoryInputError


@dataclass(frozen=True)
class TestProfile:
    name: str
    image: str


TEST_PROFILES: dict[str, TestProfile] = {
    # 标准库和 pytest 项目
    "python-basic": TestProfile(
        name="python-basic",
        image="repopilot-pytest:py311",
    ),
    # RepoPilot 自身开发验收
    "repopilot-dev": TestProfile(
        name="repopilot-dev",
        image="repopilot-pytest:repopilot-v1",
    )
}


def get_test_profile(name: str) -> TestProfile:
    # 1. 从 TEST_PROFILES 查询。
    test_profile = TEST_PROFILES.get(name)

    # 2. 找不到时抛 InvalidRepositoryInputError。
    if test_profile is None:
        raise InvalidRepositoryInputError()

    # 3. 返回对应配置。
    return test_profile