/** @type {import('next').NextConfig} */
const nextConfig = {
  experimental: {
    serverActions: { bodySizeLimit: '500mb' },
    serverComponentsExternalPackages: ['pdf-lib', 'pdf2pic', 'mammoth', 'mongodb', 'pdfjs-dist']
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
