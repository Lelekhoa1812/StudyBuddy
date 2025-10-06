/** @type {import('next').NextConfig} */
const nextConfig = {
  experimental: {
    serverActions: { bodySizeLimit: '50mb' },
    serverComponentsExternalPackages: ['pdf-parse']
  },
  webpack: (config) => {
    config.resolve = config.resolve || {}
    config.resolve.alias = {
      ...(config.resolve.alias || {}),
      canvas: false
    }
    return config
  }
}

module.exports = nextConfig
