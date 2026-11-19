/**
 * Builder X-Ray Worker.
 *
 * M0: only invoked for requests that don't match a static file. It hands them
 * back to the assets binding (which serves the 404 page). Later milestones add
 * long-tail project rendering (M4) and the payments/watchlist API (M5).
 */

export interface Env {
  ASSETS: Fetcher;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    return env.ASSETS.fetch(request);
  },
} satisfies ExportedHandler<Env>;
