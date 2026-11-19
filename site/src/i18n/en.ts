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
  pagePending: 'This page will be published before any data goes live.',
} as const;

export type Strings = typeof en;
