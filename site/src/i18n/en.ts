// All user-visible strings live here (spec §7.3). Add hi.ts / mr.ts later with the same keys.
export const en = {
  siteName: 'Builder X-Ray',
  tagline: "Every Indian builder's delivery record, from official RERA filings.",
  homeTitle: 'Builder X-Ray: delivery track records from official RERA records',
  homeDescription:
    'Search any Indian real estate builder or project and see registered completion dates, extensions and progress, each linked to the official RERA source.',
  comingSoon: 'We are building the national index. Data is not published yet.',
  footerDisclaimer: (asOf: string) =>
    `Not a credit rating. Not legal or investment advice. Based on official RERA records as of ${asOf}.`,
  footerNoData: 'No records published yet.',
  navMethodology: 'Methodology',
  navCorrections: 'Corrections',
  navRightOfReply: 'Right of Reply',
  skipToContent: 'Skip to content',
  notFoundTitle: 'Page not found',
  crawler: {
    title: 'About our crawler (BuilderXRayBot)',
    description:
      'What BuilderXRayBot is, which public RERA pages it reads, how slowly, and how to contact us or ask us to stop.',
    intro:
      'BuilderXRayBot is the automated program Builder X-Ray uses to read public pages on RERA (Real Estate Regulatory Authority) websites. If you saw it in your server logs, this page explains what it does.',
    statusHeading: 'Current status',
    status:
      'Not yet active. Crawling will begin gradually, starting with the Unified RERA portal. This page will be updated when it does.',
    userAgentHeading: 'How to recognise it',
    userAgentText: 'Every request carries this User-Agent header:',
    collectsHeading: 'What it reads',
    collects: [
      'Only pages that anyone can open in a browser without logging in.',
      'Project registration details, completion dates, extensions, quarterly progress reports and complaint or order counts.',
      'We publish counts of complaints and orders only, never complainant names.',
      'We link to original documents on the official portal instead of copying them.',
    ],
    rulesHeading: 'How it behaves',
    rules: [
      'At most one request every 3 seconds to any website, one connection at a time.',
      'It follows robots.txt and the website’s terms of use.',
      'It never logs in, never solves or bypasses CAPTCHAs, and never works around rate limits or blocks.',
      'It slows down automatically when a server returns errors, and stops after repeated errors.',
      'It fetches only pages that are new or have changed since its last visit.',
      'It runs mostly at off-peak hours (night, India time).',
    ],
    whyHeading: 'Why',
    why: 'Builder X-Ray turns public RERA records into a source-linked delivery track record for each builder and project. Every fact we publish links back to the official page it came from.',
    contactHeading: 'Contact us or ask us to stop',
    contactText:
      'If you run a RERA website and want us to slow down, avoid certain pages or stop entirely, tell us and we will comply promptly. You can also block BuilderXRayBot in robots.txt and it will obey.',
    contactLink: 'Contact the Builder X-Ray team',
  },
  pagePending: 'This page will be published before any data goes live.',
} as const;

export type Strings = typeof en;
