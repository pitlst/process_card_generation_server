import type { NextConfig } from "next"

const nextConfig: NextConfig = {
    // 静态导出模式（前端纯静态，由后端 Litestar 代理）
    output: "export",

    // 静态导出不支持 next/image 优化，关闭
    images: {
        unoptimized: true,
    },
}

export default nextConfig
