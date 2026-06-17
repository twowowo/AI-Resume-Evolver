import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "export",  // v5.1 Docker 静态导出，对接 nginx try_files
  images: {
    unoptimized: true,  // 静态导出必须禁用图片优化
  },
};

export default nextConfig;
