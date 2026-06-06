import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, type Proposal } from "../api/client";
import { Panel, Spinner, ActionBadge, fmtUsd, fmtPct } from "../components/ui";
import { SectionGuide } from "../components/SectionGuide";

type Banner = { kind: "ok" | "err"; text: string };

function qtyLabel(p: Proposal) {
  return Number.isInteger(p.qty) ? `${p.qty}` : p.qty.toFixed(2);
}

function statusClass(status: Proposal["status"]) {
  if (status === "executed") return "border-buy/40 text-buy bg-buy/10";
  if (status === "failed") return "border-sell/40 text-sell bg-sell/10";
  if (status === "pending") return "border-accent/40 text-accent bg-accent/10";
  return "border-edge text-slate-400 bg-panel2";
}

export function Automation() {
  const qc = useQueryClient();
  const [banners, setBanners] = useState<Banner[]>([]);
  const pushBanner = (kind: Banner["kind"], text: string) =>
    setBanners((b) => [{ kind, text }, ...b].slice(0, 6));

  const proposals = useQuery({
    queryKey: ["proposals", "all"],
    queryFn: () => api.proposals(""),
    refetchInterval: 15_000,
  });
  const settings = useQuery({ queryKey: ["settings"], queryFn: api.settings });

  const refreshBook = () => {
    qc.invalidateQueries({ queryKey: ["proposals"] });
    qc.invalidateQueries({ queryKey: ["portfolio"] });
    qc.invalidateQueries({ queryKey: ["orders", "open"] });
  };

  const confirm = useMutation({
    mutationFn: (p: Proposal) => api.confirmProposal(p.id),
    onSuccess: (data, p) => {
      const oid = data.proposal.result ?? data.order?.broker_order_id ?? data.order?.alpaca_order_id ?? "";
      pushBanner(
        "ok",
        `✓ Placed ${p.side.toUpperCase()} ${qtyLabel(p)} ${p.symbol}${oid ? ` (order ${oid})` : ""}`,
      );
      refreshBook();
    },
    onError: (e, p) => pushBanner("err", `✕ ${p.symbol}: ${(e as Error).message}`),
  });

  const reject = useMutation({
    mutationFn: (p: Proposal) => api.rejectProposal(p.id),
    onSuccess: (_d, p) => {
      pushBanner("ok", `Dismissed ${p.symbol} proposal`);
      refreshBook();
    },
    onError: (e) => pushBanner("err", (e as Error).message),
  });

  const confirmAll = useMutation({
    mutationFn: () => api.confirmAllProposals(),
    onSuccess: (data) => {
      const ok = data.results.filter((r) => r.ok).length;
      const fail = data.results.length - ok;
      pushBanner(
        fail ? "err" : "ok",
        `Confirmed ${ok} order${ok === 1 ? "" : "s"}${fail ? `, ${fail} failed` : ""}`,
      );
      refreshBook();
    },
    onError: (e) => pushBanner("err", (e as Error).message),
  });

  if (proposals.isLoading) return <Spinner label="Loading proposals…" />;

  const list = proposals.data?.proposals ?? [];
  const pending = list.filter((p) => p.status === "pending");
  const confirmable = pending.filter((p) => !p.blocked_reason);
  const autoOn = settings.data?.settings.auto_trade ?? false;
  const busy = confirm.isPending || reject.isPending || confirmAll.isPending;

  return (
    <div className="space-y-4">
      <SectionGuide id="automation" />
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="text-sm text-slate-400 max-w-2xl">
          Auto-trade scans the market every 15 min during market hours, records each
          proposal for audit, then auto-executes confirmable paper trades. This page now
          shows the full proposal history and signal breakdown.
        </div>
        <button
          onClick={() => confirmAll.mutate()}
          disabled={busy || confirmable.length === 0}
          className="bg-buy/20 border border-buy/40 text-buy text-sm px-4 py-1.5 rounded-lg hover:bg-buy/30 disabled:opacity-40"
        >
          {confirmAll.isPending ? "Confirming…" : `Confirm all (${confirmable.length})`}
        </button>
      </div>

      {banners.map((b, i) => (
        <div
          key={i}
          className={`rounded-xl px-4 py-2.5 text-sm border ${
            b.kind === "ok"
              ? "bg-buy/10 border-buy/40 text-buy"
              : "bg-sell/10 border-sell/40 text-sell"
          }`}
        >
          {b.text}
        </div>
      ))}

      {list.length === 0 && (
        <Panel>
          <p className="text-slate-400 text-sm py-6 text-center">
            No proposal history yet. Auto-trade is{" "}
            <span className={autoOn ? "text-buy" : "text-sell"}>{autoOn ? "ON" : "OFF"}</span>.
            {!autoOn && (
              <>
                {" "}
                Enable it in{" "}
                <Link to="/settings" className="text-accent hover:underline">
                  Settings → Automation
                </Link>
                .
              </>
            )}
          </p>
        </Panel>
      )}

      <div className="space-y-2">
        {list.map((p) => (
          <ProposalCard
            key={p.id}
            p={p}
            busy={busy}
            confirming={confirm.isPending && confirm.variables?.id === p.id}
            rejecting={reject.isPending && reject.variables?.id === p.id}
            onConfirm={() => confirm.mutate(p)}
            onReject={() => reject.mutate(p)}
          />
        ))}
      </div>
    </div>
  );
}

function ProposalCard({
  p,
  busy,
  confirming,
  rejecting,
  onConfirm,
  onReject,
}: {
  p: Proposal;
  busy: boolean;
  confirming: boolean;
  rejecting: boolean;
  onConfirm: () => void;
  onReject: () => void;
}) {
  const blocked = !!p.blocked_reason;
  return (
    <Panel className="!p-0 overflow-hidden">
      <div className="flex items-start gap-4 px-4 py-3">
        <div className="w-20 shrink-0">
          <Link to={`/ticker/${p.symbol}`} className="font-bold text-lg hover:text-accent">
            {p.symbol}
          </Link>
        </div>
        <ActionBadge action={p.side.toUpperCase()} />
        <div className="flex-1 min-w-0">
          <div className="text-sm text-slate-200">
            <span className="font-semibold">{qtyLabel(p)} sh</span>
            <span className="text-slate-400"> · {fmtUsd(p.est_cost)} est.</span>
            {p.equity_pct != null && (
              <span className="text-slate-500"> · {fmtPct(p.equity_pct, 1)} of equity</span>
            )}
            <span className="text-slate-500"> · @ {fmtUsd(p.price)}</span>
          </div>
          <div className="flex flex-wrap gap-2 mt-1 text-[11px]">
            <span className={`px-2 py-0.5 rounded border ${statusClass(p.status)}`}>
              {p.status.toUpperCase()}{p.result ? ` · ${p.result}` : ""}
            </span>
            {p.created_at && <span className="text-slate-500">Proposed {new Date(p.created_at).toLocaleString()}</span>}
            {p.decided_at && <span className="text-slate-500">Decided {new Date(p.decided_at).toLocaleString()}</span>}
          </div>
          <p className="text-xs text-slate-400 mt-1">{p.rationale}</p>
          {blocked && (
            <p className="text-xs text-sell mt-1">⚠ Can't place: {p.blocked_reason}</p>
          )}
          <details className="mt-2 text-xs text-slate-400">
            <summary className="cursor-pointer hover:text-slate-200">Why this stock was chosen</summary>
            <div className="mt-2 space-y-2">
              {p.reasons.length > 0 && (
                <ul className="list-disc pl-5 space-y-1">
                  {p.reasons.map((r, i) => <li key={i}>{r}</li>)}
                </ul>
              )}
              {Object.keys(p.breakdown ?? {}).length > 0 ? (
                <div className="grid md:grid-cols-2 gap-2">
                  {Object.entries(p.breakdown ?? {}).map(([name, b]) => (
                    <div key={name} className="rounded-lg border border-edge bg-panel2 p-2">
                      <div className="flex justify-between gap-2 text-slate-300">
                        <span className="capitalize font-semibold">{name}</span>
                        <span>score {typeof b.score === "number" ? b.score.toFixed(2) : b.score} · weight {fmtPct(b.weight ?? 0, 0)}</span>
                      </div>
                      {b.reasons?.length > 0 && (
                        <ul className="list-disc pl-4 mt-1 space-y-0.5">
                          {b.reasons.map((r, i) => <li key={i}>{r}</li>)}
                        </ul>
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-slate-500">Older proposal: detailed per-signal breakdown was not stored yet.</p>
              )}
            </div>
          </details>
        </div>
        {p.status === "pending" && (
          <div className="flex gap-2 shrink-0">
            <button
              onClick={onConfirm}
              disabled={busy || blocked}
              title={blocked ? p.blocked_reason ?? "" : `Confirm ${p.side} ${p.symbol} (paper)`}
              className="bg-buy/20 border border-buy/40 text-buy text-xs px-3 py-1.5 rounded-lg hover:bg-buy/30 disabled:opacity-30"
            >
              {confirming ? "…" : "Confirm"}
            </button>
            <button
              onClick={onReject}
              disabled={busy}
              className="bg-panel2 border border-edge text-slate-300 text-xs px-3 py-1.5 rounded-lg hover:bg-edge disabled:opacity-40"
            >
              {rejecting ? "…" : "Reject"}
            </button>
          </div>
        )}
      </div>
    </Panel>
  );
}
