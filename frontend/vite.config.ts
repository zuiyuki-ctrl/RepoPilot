import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  // 不加载仓库根目录配置，也不向浏览器注入服务端环境变量。
  envDir: './client-env',
  server: { host: '127.0.0.1', fs: { allow: ['.', '../assets'] } },
})
