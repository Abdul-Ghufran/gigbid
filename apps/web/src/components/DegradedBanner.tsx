import { api, call, type SystemStatus } from "../lib/api/client";
import { useLoad } from "../lib/hooks";

/** Polls /api/system/status; when the marketplace MCP server is down, tells the user that work is queued. */
export function DegradedBanner() {
  const { data } = useLoad<SystemStatus>(() => call(api.GET("/api/system/status")), [], 15000);
  if (!data) return null;
  return (
    <>
      {data.marketplace === "down" && (
        <div className="banner banner-bad" role="alert" data-testid="degraded-banner">
          <strong>Marketplace unavailable.</strong> GigBid cannot reach the {data.marketplace_mode === "gigsim" ? "GigSim" : "Upwork"} marketplace
          right now. New scouting and submissions are queued and will resume automatically; your drafts and approvals are safe.
        </div>
      )}
      {data.llm_offline && (
        <div className="banner banner-warn" role="status">Model provider offline: GigBid is using its deterministic fallbacks.</div>
      )}
    </>
  );
}
