// @ts-check
import { defineConfig } from 'astro/config';

export default defineConfig({
  output: 'static',
  // Replaced with the real domain at M4; used for canonical URLs and sitemaps.
  site: 'https://builder-xray.workers.dev',
  trailingSlash: 'always',
  build: {
    format: 'directory',
    // Keep CSS in external files so the CSP can forbid inline styles/scripts.
    inlineStylesheets: 'never',
  },
  compressHTML: true,
});
