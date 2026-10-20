<script setup lang="ts">
export type IconName = 'dashboard' | 'experiment' | 'run' | 'agent' | 'benchmark' | 'report' | 'archive' | 'compare' | 'menu' | 'close' | 'refresh' | 'arrow' | 'chevron'
withDefaults(defineProps<{ name: IconName; size?: number }>(), { size: 20 })
const paths: Record<IconName, string> = {
  dashboard: 'M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z',
  experiment: 'M9 3h6 M10 3v6L4 19a1.3 1.3 0 0 0 1.2 2h13.6A1.3 1.3 0 0 0 20 19L14 9V3 M7 14h10',
  run: 'M9 6l10 6-10 6z M4 5v14',
  agent: 'M9 3h6v4 M5 7h14v13H5z M9 12v2 M15 12v2 M9 17h6 M2 11v5 M22 11v5',
  benchmark: 'M5 4h14v17H5z M9 4V2h6v2 M8 10l1 1 2-2 M13 10h3 M8 16l1 1 2-2 M13 16h3',
  report: 'M5 3h9l5 5v13H5z M14 3v6h5 M9 13h6 M9 17h6',
  archive: 'M3 4h18v4H3z M5 8v13h14V8 M9 12h6',
  compare: 'M4 7h16 M16 3l4 4-4 4 M20 17H4 M8 13l-4 4 4 4',
  menu: 'M4 6h16 M4 12h16 M4 18h16', close: 'M6 6l12 12 M18 6L6 18',
  refresh: 'M20 8a8 8 0 1 0 0 8 M20 3v5h-5', arrow: 'M4 12h16 M14 6l6 6-6 6', chevron: 'M9 5l7 7-7 7',
}
</script>
<template><svg :width="size" :height="size" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><path :d="paths[name]" /></svg></template>
