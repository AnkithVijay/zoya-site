// Zoya Deals click tracker: GET /functions/v1/go?p=<product_id>  (legacy: ?d=<id>)
// Logs a click (referrer, country, sha-256 of UA; never the IP) and 302s to the store
// with the affiliate tag from public.config. Deployed with verify_jwt = false.
import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { createClient } from "npm:@supabase/supabase-js@2";

const db = createClient(
  Deno.env.get("SUPABASE_URL")!,
  Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!,
  { auth: { persistSession: false } },
);
const ID_RE = /^[a-z0-9][a-z0-9-]{0,80}$/;
// Old ids from before the products restructure (2026-10-23), so stale links keep working.
const LEGACY: Record<string, string> = { "nord-buds-3r": "oneplus-nord-buds-3r" };

async function sha256(s: string): Promise<string> {
  const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(s));
  return Array.from(new Uint8Array(buf)).map((b) => b.toString(16).padStart(2, "0")).join("");
}

function withTag(url: string, store: string, cfg: { amazon_tag?: string; flipkart_affid?: string } | null): string {
  try {
    const u = new URL(url);
    const tag = store === "flipkart" ? cfg?.flipkart_affid : store === "amazon" ? cfg?.amazon_tag : "";
    const key = store === "flipkart" ? "affid" : "tag";
    if (tag && tag.trim()) u.searchParams.set(key, tag.trim());
    return u.toString();
  } catch {
    return url;
  }
}

const text = (body: string, status: number) =>
  new Response(body, { status, headers: { "content-type": "text/plain; charset=utf-8", "cache-control": "no-store" } });

Deno.serve(async (req) => {
  if (req.method !== "GET" && req.method !== "HEAD") return text("Method not allowed", 405);
  const qs = new URL(req.url).searchParams;
  let id = (qs.get("p") || qs.get("d") || "").trim().toLowerCase();
  id = LEGACY[id] || id;
  if (!ID_RE.test(id)) return text("Product not found", 404);

  const [{ data: product, error }, { data: cfg }] = await Promise.all([
    db.from("products").select("product_id, store, product_url, active").eq("product_id", id).maybeSingle(),
    db.from("config").select("amazon_tag, flipkart_affid").eq("id", true).maybeSingle(),
  ]);
  if (error) { console.error("product lookup", error); return text("Temporarily unavailable", 503); }
  if (!product || !product.active) return text("Product not found", 404);

  const target = withTag(product.product_url, product.store, cfg);

  // Don't count HEAD probes or obvious link-preview bots as clicks.
  const ua = req.headers.get("user-agent") || "";
  const isBot = /bot|crawl|spider|preview|facebookexternalhit|whatsapp|slurp|curl\/|wget/i.test(ua);
  if (req.method === "GET" && !isBot) {
    const country = req.headers.get("cf-ipcountry") || req.headers.get("x-country") ||
      req.headers.get("x-vercel-ip-country") || null;
    const referrer = (req.headers.get("referer") || "").slice(0, 500) || null;
    const { error: e2 } = await db.from("clicks").insert({
      product_id: product.product_id,
      referrer,
      country: country && country !== "XX" ? country.slice(0, 8) : null,
      ua_hash: ua ? await sha256(ua) : null,
    });
    if (e2) console.error("click insert", e2);
  }

  return new Response(null, {
    status: 302,
    headers: {
      location: target,
      "cache-control": "no-store",
      "referrer-policy": "no-referrer",
      "x-robots-tag": "noindex, nofollow",
    },
  });
});
