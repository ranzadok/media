// תגיד · חיבורים למורנינג ול-Grow של בעל המקצוע
// קריאה מהאפליקציה: functions.invoke("integrations", { body: { action, ... } })
// פעולות: status | connect | disconnect | morning_doc | grow_link | docs
// סודות נדרשים: INTEGRATIONS_KEY (24 תווים ומעלה). רשות: MORNING_BASE, GROW_BASE, GROW_PLATFORM_API_KEY, INTEG_HOOK_SECRET, TAGID_SITE
import { createClient } from "npm:@supabase/supabase-js@2";

// ---- לוגיקה (core.ts) ----
// תגיד · חיבורים: לוגיקה טהורה (בלי Supabase), כדי שאפשר לבדוק אותה לבד.
// שני ספקים: morning (מסמכים) ו-grow (קישור תשלום). תגיד לא מפיקה מסמך מס בעצמה ולא מחזיקה כסף.

type Line = { name: string; qty: number; unit: number };
type Quote = { number: string; client: string; phone?: string; email?: string; lines: Line[]; discountPct?: number; vatExempt?: boolean };
type Fetch = (url: string, init?: RequestInit) => Promise<Response>;

const r2 = (n: number) => Math.round(n * 100) / 100;
const VAT = 0.18;

// ---- בדיקת קלט: לא סומכים על מה שמגיע מהאפליקציה ----
function cleanQuote(q: unknown): Quote | null {
  const o = (q ?? {}) as Record<string, unknown>;
  const number = String(o.number ?? "").trim().slice(0, 40);
  const client = String(o.client ?? "").trim().slice(0, 120);
  const raw = Array.isArray(o.lines) ? o.lines : [];
  const lines: Line[] = [];
  for (const l of raw.slice(0, 60)) {
    const x = (l ?? {}) as Record<string, unknown>;
    const name = String(x.name ?? "").trim().slice(0, 200), qty = Number(x.qty), unit = Number(x.unit);
    if (!name || !(qty > 0) || !(unit >= 0) || !isFinite(qty) || !isFinite(unit)) return null;
    lines.push({ name, qty: r2(qty), unit: r2(unit) });
  }
  if (!number || !client || !lines.length) return null;
  const d = Number(o.discountPct ?? 0);
  const phone = String(o.phone ?? "").replace(/[^\d+]/g, "").slice(0, 20) || undefined;
  const email = String(o.email ?? "").trim().slice(0, 120);
  return { number, client, phone, email: /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(email) ? email : undefined, lines, discountPct: d > 0 && d <= 100 ? r2(d) : 0, vatExempt: !!o.vatExempt };
}
function totals(q: Quote) {
  const gross = r2(q.lines.reduce((s, l) => s + l.unit * l.qty, 0));
  const sum = r2(gross * (1 - (q.discountPct ?? 0) / 100));
  const vat = q.vatExempt ? 0 : r2(sum * VAT);
  return { gross, sum, vat, total: r2(sum + vat) };
}

// ---- הצפנת המפתחות של בעל המקצוע (AES-GCM, מפתח מהסביבה) ----
async function key(secret: string) {
  if (!secret || secret.length < 24) throw new Error("INTEGRATIONS_KEY חסר או קצר מדי");
  const h = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(secret));
  return crypto.subtle.importKey("raw", h, "AES-GCM", false, ["encrypt", "decrypt"]);
}
const b64 = (u: Uint8Array) => btoa(String.fromCharCode(...u));
const unb64 = (s: string) => Uint8Array.from(atob(s), c => c.charCodeAt(0));
async function seal(secret: string, data: unknown): Promise<string> {
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const ct = new Uint8Array(await crypto.subtle.encrypt({ name: "AES-GCM", iv }, await key(secret), new TextEncoder().encode(JSON.stringify(data))));
  return `v1.${b64(iv)}.${b64(ct)}`;
}
async function open<T>(secret: string, sealed: string): Promise<T> {
  const [v, iv, ct] = sealed.split(".");
  if (v !== "v1" || !iv || !ct) throw new Error("bad sealed value");
  const pt = await crypto.subtle.decrypt({ name: "AES-GCM", iv: unb64(iv) }, await key(secret), unb64(ct));
  return JSON.parse(new TextDecoder().decode(pt)) as T;
}

// ---- מורנינג ----
type MorningCreds = { id: string; secret: string };
// סוגי מסמכים במורנינג: 300 חשבון עסקה (דרישת תשלום), 305 חשבונית מס
const MORNING_TYPE = { request: 300, invoice: 305 } as const;
type MorningKind = keyof typeof MORNING_TYPE;

async function morningToken(base: string, c: MorningCreds, f: Fetch = fetch): Promise<string> {
  const r = await f(`${base}/account/token`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ id: c.id, secret: c.secret }) });
  const j = await r.json().catch(() => ({}));
  if (!r.ok || !j.token) throw new ProviderError("morning_auth", j.errorMessage ?? `HTTP ${r.status}`);
  return String(j.token);
}
async function morningBusiness(base: string, token: string, f: Fetch = fetch): Promise<string> {
  const r = await f(`${base}/businesses/me`, { headers: { Authorization: `Bearer ${token}` } });
  const j = await r.json().catch(() => ({}));
  return r.ok ? String(j.name ?? "") : "";
}
// הופך הצעה של תגיד למסמך של מורנינג. המחירים בתגיד הם לפני מע״מ.
function morningPayload(q: Quote, kind: MorningKind, today = new Date()) {
  const d = (q.discountPct ?? 0) / 100;
  return {
    description: `הצעה ${q.number}`,
    type: MORNING_TYPE[kind],
    date: today.toISOString().slice(0, 10),
    lang: "he",
    currency: "ILS",
    vatType: 0,                    // לפי סוג העסק במורנינג (פטור / מורשה)
    discount: d > 0 ? { amount: q.discountPct, type: "percentage" } : undefined,
    client: { name: q.client, phone: q.phone, emails: q.email ? [q.email] : undefined, add: true },
    income: q.lines.map(l => ({ description: l.name, quantity: l.qty, price: l.unit, currency: "ILS", vatType: 0 })),
    remarks: "הופק מתגיד",
  };
}
async function morningCreate(base: string, token: string, payload: unknown, f: Fetch = fetch) {
  const r = await f(`${base}/documents`, { method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` }, body: JSON.stringify(payload) });
  const j = await r.json().catch(() => ({}));
  if (!r.ok || !j.id) throw new ProviderError("morning_doc", j.errorMessage ?? `HTTP ${r.status}`, j.errorCode);
  return { id: String(j.id), number: j.number != null ? String(j.number) : "", url: String(j.url?.he ?? j.url?.origin ?? "") };
}

// ---- Grow ----
type GrowCreds = { userId: string; pageCode: string };
function growParams(c: GrowCreds, q: Quote, o: { sum: number; fullName: string; phone: string; successUrl: string; cancelUrl: string; notifyUrl: string; platformKey?: string; ref: string }) {
  const p: Record<string, string> = {
    pageCode: c.pageCode, userId: c.userId, sum: o.sum.toFixed(2),
    description: `הצעה ${q.number}`.slice(0, 100),
    successUrl: o.successUrl, cancelUrl: o.cancelUrl, notifyUrl: o.notifyUrl,
    "pageField[fullName]": o.fullName, "pageField[phone]": o.phone,
    cField1: o.ref,
  };
  if (q.email) p["pageField[email]"] = q.email;
  if (o.platformKey) p.apiKey = o.platformKey;
  return p;
}
async function growCreate(base: string, params: Record<string, string>, f: Fetch = fetch) {
  const fd = new FormData();
  for (const [k, v] of Object.entries(params)) fd.append(k, v);
  const r = await f(`${base}/createPaymentProcess`, { method: "POST", body: fd });
  const text = await r.text();
  let j: Record<string, any> = {};
  try { j = JSON.parse(text); } catch { /* לא JSON */ }
  const url = j?.data?.url ?? j?.url;
  if (!url) throw new ProviderError("grow_link", j?.err?.message ?? j?.err ?? `HTTP ${r.status}`);
  return { url: String(url), processId: String(j?.data?.processId ?? "") };
}

class ProviderError extends Error {
  constructor(public reason: string, public detail: unknown, public code?: unknown) { super(String(reason)); }
}

// ---- הפונקציה ----

const cors = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { ...cors, "Content-Type": "application/json" } });

// ברירת המחדל היא סביבות הבדיקה. עוברים לאמת רק בהגדרת הסוד במפורש.
const MORNING_BASE = Deno.env.get("MORNING_BASE") ?? "https://sandbox.d.greeninvoice.co.il/api/v1";
const GROW_BASE = Deno.env.get("GROW_BASE") ?? "https://sandbox.meshulam.co.il/api/light/server/1.0";
const SITE = Deno.env.get("TAGID_SITE") ?? "https://tagid.co.il";
const KEY = Deno.env.get("INTEGRATIONS_KEY") ?? "";
const HOOK = Deno.env.get("INTEG_HOOK_SECRET") ?? "";
const FN = `${Deno.env.get("SUPABASE_URL")}/functions/v1/integrations`;
const admin = () => createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!);

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: cors });
  const url = new URL(req.url);
  try {
    // ---- הודעה מ-Grow על תשלום (לא מהאפליקציה) ----
    if (url.searchParams.get("hook") === "grow") {
      if (!HOOK || url.searchParams.get("k") !== HOOK) return json({ ok: false }, 403);
      const fd = await req.formData().catch(() => null);
      const flat: Record<string, string> = {};
      if (fd) for (const [k, v] of fd.entries()) flat[k] = String(v);
      const find = (n: string) => { for (const [k, v] of Object.entries(flat)) if (v && (k === n || k.endsWith(`[${n}]`))) return v; return ""; };
      const ref = find("cField1"), paid = (find("status") || "1") === "1" && !!(find("transactionId") || find("asmachta"));
      if (ref && paid) await admin().from("integration_docs").update({ status: "paid", updated_at: new Date().toISOString() }).eq("id", ref).eq("provider", "grow");
      return json({ ok: true });
    }

    const auth = req.headers.get("Authorization") ?? "";
    const user = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_ANON_KEY")!, { global: { headers: { Authorization: auth } } });
    const { data: { user: u } } = await user.auth.getUser();
    if (!u) return json({ ok: false, reason: "not_signed_in" }, 401);
    const db = admin();
    const body = await req.json().catch(() => ({}));
    const action = String(body.action ?? "");
    const row = async (provider: string) => (await db.from("integrations").select("*").eq("business_id", u.id).eq("provider", provider).maybeSingle()).data;

    if (action === "status") {
      const { data } = await db.from("integrations").select("provider,label,verified,created_at").eq("business_id", u.id);
      return json({ ok: true, list: data ?? [] });
    }

    if (action === "disconnect") {
      const provider = String(body.provider);
      if (!["morning", "grow"].includes(provider)) return json({ ok: false, reason: "provider" }, 400);
      await db.from("integrations").delete().eq("business_id", u.id).eq("provider", provider);
      return json({ ok: true });
    }

    if (action === "connect") {
      if (!KEY) return json({ ok: false, reason: "server_not_ready" }, 503);
      const provider = String(body.provider);
      if (provider === "morning") {
        const c: MorningCreds = { id: String(body.id ?? "").trim(), secret: String(body.secret ?? "").trim() };
        if (c.id.length < 8 || c.secret.length < 8) return json({ ok: false, reason: "creds" }, 400);
        const token = await morningToken(MORNING_BASE, c);          // נכשל כאן אם המפתח שגוי או שהמסלול לא כולל API
        const label = await morningBusiness(MORNING_BASE, token);
        await db.from("integrations").upsert({ business_id: u.id, provider, creds: await seal(KEY, c), label, verified: true, updated_at: new Date().toISOString() });
        return json({ ok: true, label, verified: true });
      }
      if (provider === "grow") {
        const c: GrowCreds = { userId: String(body.userId ?? "").trim(), pageCode: String(body.pageCode ?? "").trim() };
        if (c.userId.length < 6 || c.pageCode.length < 6) return json({ ok: false, reason: "creds" }, 400);
        // אין ב-Grow בדיקת מזהים בלי ליצור תשלום, ולכן החיבור נשמר כ"לא מאומת" עד הקישור הראשון שמצליח
        await db.from("integrations").upsert({ business_id: u.id, provider, creds: await seal(KEY, c), label: null, verified: false, updated_at: new Date().toISOString() });
        return json({ ok: true, verified: false });
      }
      return json({ ok: false, reason: "provider" }, 400);
    }

    if (action === "docs") {
      const { data } = await db.from("integration_docs").select("provider,kind,ext_number,url,amount,status,created_at").eq("business_id", u.id).eq("quote_no", String(body.quoteNo ?? "")).order("created_at");
      return json({ ok: true, list: data ?? [] });
    }

    if (action === "morning_doc") {
      const kind = String(body.kind) as MorningKind;
      if (!(kind in MORNING_TYPE)) return json({ ok: false, reason: "kind" }, 400);
      const q = cleanQuote(body.quote);
      if (!q) return json({ ok: false, reason: "quote" }, 400);
      const r = await row("morning");
      if (!r) return json({ ok: false, reason: "not_connected" }, 409);
      // לא יוצרים פעמיים: מסמך מס שנוצר אי אפשר למחוק
      const { data: ex } = await db.from("integration_docs").select("*").eq("business_id", u.id).eq("provider", "morning").eq("kind", kind).eq("quote_no", q.number).maybeSingle();
      if (ex) return json({ ok: true, existing: true, number: ex.ext_number, url: ex.url });
      const token = await morningToken(MORNING_BASE, await open<MorningCreds>(KEY, r.creds));
      const doc = await morningCreate(MORNING_BASE, token, morningPayload(q, kind));
      await db.from("integration_docs").insert({ business_id: u.id, provider: "morning", kind, quote_no: q.number, ext_id: doc.id, ext_number: doc.number, url: doc.url, amount: totals(q).total });
      return json({ ok: true, number: doc.number, url: doc.url });
    }

    if (action === "grow_link") {
      const q = cleanQuote(body.quote);
      if (!q) return json({ ok: false, reason: "quote" }, 400);
      const t = totals(q), sum = Number(body.sum ?? t.total);
      if (!(sum > 0) || sum > t.total + 0.01) return json({ ok: false, reason: "sum" }, 400);   // אי אפשר לבקש יותר מסכום ההצעה
      const phone = String(q.phone ?? "").replace(/\D/g, "");
      if (q.client.split(/\s+/).length < 2) return json({ ok: false, reason: "full_name" }, 400);
      if (!/^05\d{8}$/.test(phone)) return json({ ok: false, reason: "phone" }, 400);
      const r = await row("grow");
      if (!r) return json({ ok: false, reason: "not_connected" }, 409);
      const kind = sum < t.total - 0.01 ? "deposit" : "paylink";
      const { data: ex } = await db.from("integration_docs").select("*").eq("business_id", u.id).eq("provider", "grow").eq("kind", kind).eq("quote_no", q.number).maybeSingle();
      if (ex?.url && Number(ex.amount) === sum) return json({ ok: true, existing: true, url: ex.url, status: ex.status });
      const { data: rec, error } = await db.from("integration_docs").upsert({ business_id: u.id, provider: "grow", kind, quote_no: q.number, amount: sum, status: "created", updated_at: new Date().toISOString() }, { onConflict: "business_id,provider,kind,quote_no" }).select().single();
      if (error || !rec) return json({ ok: false, reason: "db" }, 500);
      const res = await growCreate(GROW_BASE, growParams(await open<GrowCreds>(KEY, r.creds), q, {
        sum, fullName: q.client, phone, ref: rec.id,
        successUrl: `${SITE}/q/?paid=1`, cancelUrl: `${SITE}/q/?paid=0`,
        notifyUrl: `${FN}?hook=grow&k=${HOOK}`, platformKey: Deno.env.get("GROW_PLATFORM_API_KEY") ?? undefined,
      }));
      await db.from("integration_docs").update({ url: res.url, ext_id: res.processId }).eq("id", rec.id);
      if (!r.verified) await db.from("integrations").update({ verified: true }).eq("business_id", u.id).eq("provider", "grow");
      return json({ ok: true, url: res.url });
    }

    return json({ ok: false, reason: "action" }, 400);
  } catch (e) {
    if (e instanceof ProviderError) return json({ ok: false, reason: e.reason, detail: e.detail, code: e.code ?? null }, 502);
    return json({ ok: false, reason: "error", detail: String(e) }, 500);
  }
});
