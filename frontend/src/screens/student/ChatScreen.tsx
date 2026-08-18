/* ChatScreen (student) — grounded Q&A with [N] citations. Ported from
 * fr-screens-student.jsx, wired to the SSE chat endpoint via ApiClient.streamChat.
 *
 * Q2 (resolved): the stream carries only answer text with inline [N] markers —
 * citations are extracted server-side and persisted, never streamed, and there is
 * no messages GET route. So we parse [N] from the text and build the sources panel
 * from the distinct markers. Real filenames/locators aren't exposed to the client,
 * so each source is labelled "Source [N]"; the honesty guardrail copy (R-FE4) is
 * kept verbatim from the mock. */
import { useEffect, useMemo, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';

import { Icon } from '@/components/Icon';
import { Alert } from '@/components/ui/Alert';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Citation, SourceChip } from '@/components/ui/Citation';
import { Avatar } from '@/components/ui/Avatar';
import { Input } from '@/components/ui/inputs';
import { useApi } from '@/lib/auth';
import { useNotebooks } from '@/lib/query';

type Part = { t: string } | { c: number };

function toParts(text: string): Part[] {
  const parts: Part[] = [];
  const re = /\[(\d+)\]/g;
  let last = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) parts.push({ t: text.slice(last, m.index) });
    parts.push({ c: parseInt(m[1], 10) });
    last = m.index + m[0].length;
  }
  if (last < text.length) parts.push({ t: text.slice(last) });
  return parts;
}

function citationNumbers(text: string): number[] {
  const seen = new Set<number>();
  const out: number[] = [];
  for (const m of text.matchAll(/\[(\d+)\]/g)) {
    const n = parseInt(m[1], 10);
    if (!seen.has(n)) {
      seen.add(n);
      out.push(n);
    }
  }
  return out;
}

interface Message {
  role: 'user' | 'assistant';
  text: string;
  streaming?: boolean;
  error?: string;
}

const SUGGESTIONS = [
  'How does photosynthesis store energy?',
  'Where does the Calvin cycle happen?',
  'What are the light-dependent reactions?',
];

export function ChatScreen() {
  const api = useApi();
  const [params] = useSearchParams();
  const notebooks = useNotebooks();
  const notebookId = params.get('nb') ?? notebooks.data?.[0]?.id ?? '';
  const notebookTitle = notebooks.data?.find((n) => n.id === notebookId)?.title ?? 'this notebook';

  const [thread, setThread] = useState<Message[]>([]);
  const [draft, setDraft] = useState('');
  const [busy, setBusy] = useState(false);
  const [active, setActive] = useState<number | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [thread]);

  const lastAssistant = [...thread].reverse().find((m) => m.role === 'assistant' && m.text);
  const sources = useMemo(
    () => (lastAssistant ? citationNumbers(lastAssistant.text) : []),
    [lastAssistant],
  );

  const ask = async (q?: string) => {
    const question = (q ?? draft).trim();
    if (!question || busy || !api || !notebookId) return;
    setDraft('');
    setActive(null);
    setThread((t) => [
      ...t,
      { role: 'user', text: question },
      { role: 'assistant', text: '', streaming: true },
    ]);
    setBusy(true);

    const patchLast = (patch: Partial<Message>) =>
      setThread((t) => {
        const copy = [...t];
        copy[copy.length - 1] = { ...copy[copy.length - 1], ...patch };
        return copy;
      });

    try {
      for await (const tok of api.streamChat({ notebookId, question })) {
        setThread((t) => {
          const copy = [...t];
          const last = copy[copy.length - 1];
          copy[copy.length - 1] = { ...last, text: last.text + tok };
          return copy;
        });
      }
      patchLast({ streaming: false });
    } catch (e) {
      patchLast({ streaming: false, error: (e as Error).message });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div style={{ display: 'flex', height: '100%', minHeight: 0 }}>
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
        <div ref={scrollRef} style={{ flex: 1, overflowY: 'auto', padding: '26px 30px' }}>
          <div
            style={{
              maxWidth: 720,
              margin: '0 auto',
              display: 'flex',
              flexDirection: 'column',
              gap: 18,
            }}
          >
            {thread.length === 0 && (
              <div style={{ textAlign: 'center', padding: '44px 0 8px' }}>
                <span
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    width: 64,
                    height: 64,
                    borderRadius: 22,
                    background: 'var(--fr-accent-soft)',
                    marginBottom: 16,
                  }}
                >
                  <Icon name="sparkles" size={30} color="var(--fr-accent)" />
                </span>
                <h3
                  style={{
                    color: 'var(--text-strong)',
                    fontSize: 21,
                    fontWeight: 800,
                    margin: '0 0 8px',
                    letterSpacing: '-0.01em',
                  }}
                >
                  Ask me anything about this notebook
                </h3>
                <p
                  style={{
                    fontSize: 14.5,
                    color: 'var(--text-muted)',
                    margin: '0 auto 22px',
                    maxWidth: 440,
                    lineHeight: 1.55,
                  }}
                >
                  I only answer from <b style={{ color: 'var(--text-body)' }}>{notebookTitle}</b>,
                  and I&apos;ll show you exactly where every answer comes from with <code>[N]</code>{' '}
                  citations.
                </p>
                <div
                  style={{ display: 'flex', gap: 9, justifyContent: 'center', flexWrap: 'wrap' }}
                >
                  {SUGGESTIONS.map((s) => (
                    <button
                      key={s}
                      onClick={() => ask(s)}
                      style={{
                        display: 'inline-flex',
                        alignItems: 'center',
                        gap: 7,
                        padding: '10px 15px',
                        border: '1.5px solid var(--border)',
                        borderRadius: 999,
                        background: '#fff',
                        color: 'var(--text-body)',
                        fontSize: 13.5,
                        fontWeight: 500,
                        cursor: 'pointer',
                        fontFamily: 'var(--font-sans)',
                        boxShadow: 'var(--fr-shadow-card)',
                      }}
                    >
                      <Icon name="messageCircle" size={14} color="var(--fr-accent)" /> {s}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {thread.map((m, i) =>
              m.role === 'user' ? (
                <div key={i} style={{ display: 'flex', justifyContent: 'flex-end', gap: 11 }}>
                  <div
                    style={{
                      maxWidth: '76%',
                      background: 'var(--fr-accent)',
                      color: '#fff',
                      padding: '12px 16px',
                      borderRadius: '18px 18px 5px 18px',
                      fontSize: 14.5,
                      lineHeight: 1.55,
                      boxShadow: '0 4px 14px -6px rgba(79,70,229,.45)',
                    }}
                  >
                    {m.text}
                  </div>
                </div>
              ) : (
                <div key={i} style={{ display: 'flex', gap: 12 }}>
                  <Avatar name="ASAG" role="ai" size={34} />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    {m.text === '' && m.streaming ? (
                      <div
                        style={{
                          background: '#fff',
                          border: '1px solid var(--border-faint)',
                          borderRadius: '5px 18px 18px 18px',
                          padding: '16px 18px',
                          boxShadow: 'var(--fr-shadow-card)',
                          display: 'flex',
                          gap: 5,
                          alignItems: 'center',
                        }}
                      >
                        {[0, 1, 2].map((d) => (
                          <span
                            key={d}
                            style={{
                              width: 7,
                              height: 7,
                              borderRadius: 999,
                              background: 'var(--indigo-300)',
                              animation: `fr-bounce 1.1s ${d * 0.15}s ease-in-out infinite`,
                            }}
                          />
                        ))}
                      </div>
                    ) : m.error ? (
                      <Alert tone="danger" icon={<Icon name="alert" size={16} />}>
                        {m.error}
                      </Alert>
                    ) : (
                      <>
                        <div
                          style={{
                            background: '#fff',
                            border: '1px solid var(--border-faint)',
                            borderRadius: '5px 18px 18px 18px',
                            padding: '15px 18px',
                            fontSize: 14.5,
                            lineHeight: 1.75,
                            color: 'var(--text-body)',
                            boxShadow: 'var(--fr-shadow-card)',
                          }}
                        >
                          {toParts(m.text).map((p, j) =>
                            't' in p ? (
                              <span key={j}>{p.t}</span>
                            ) : (
                              <Citation
                                key={j}
                                n={p.c}
                                active={active === p.c}
                                onClick={() => setActive(p.c)}
                                title={`Source ${p.c}`}
                              />
                            ),
                          )}
                        </div>
                        {!m.streaming && citationNumbers(m.text).length > 0 && (
                          <div
                            style={{
                              display: 'flex',
                              alignItems: 'center',
                              gap: 7,
                              marginTop: 9,
                              fontSize: 12.5,
                              color: 'var(--text-muted)',
                            }}
                          >
                            <span
                              style={{
                                display: 'inline-flex',
                                alignItems: 'center',
                                gap: 5,
                                padding: '3px 9px',
                                borderRadius: 999,
                                background: 'var(--green-50)',
                                color: 'var(--green-700)',
                                fontWeight: 600,
                              }}
                            >
                              <Icon name="shield" size={13} color="var(--green-600)" /> Grounded in{' '}
                              {citationNumbers(m.text).length} sources
                            </span>
                            <span>
                              Tap any <code>[N]</code> to see the source →
                            </span>
                          </div>
                        )}
                      </>
                    )}
                  </div>
                </div>
              ),
            )}
          </div>
        </div>

        <div
          style={{ borderTop: '1px solid var(--border)', background: '#fff', padding: '16px 30px' }}
        >
          <div
            style={{
              maxWidth: 720,
              margin: '0 auto',
              display: 'flex',
              gap: 11,
              alignItems: 'center',
            }}
          >
            <div style={{ flex: 1 }}>
              <Input
                placeholder="Ask a question about this notebook…"
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') ask();
                }}
              />
            </div>
            <Button
              size="lg"
              iconRight={<Icon name="send" size={17} />}
              onClick={() => ask()}
              disabled={busy}
            >
              Ask
            </Button>
          </div>
          <p
            style={{
              maxWidth: 720,
              margin: '10px auto 0',
              fontSize: 12,
              color: 'var(--text-faint)',
              textAlign: 'center',
            }}
          >
            If the materials don&apos;t cover your question, ASAG says so honestly instead of
            guessing.
          </p>
        </div>
      </div>

      <aside
        style={{
          width: 300,
          flex: 'none',
          borderLeft: '1px solid var(--border)',
          background: '#fff',
          padding: '22px 18px',
          overflowY: 'auto',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 14 }}>
          <Icon name="layers" size={17} color="var(--fr-accent)" />
          <b style={{ fontSize: 14, color: 'var(--text-strong)' }}>Sources</b>
          <Badge tone="brand">{sources.length}</Badge>
        </div>
        {sources.length === 0 ? (
          <p style={{ fontSize: 13, color: 'var(--text-muted)', lineHeight: 1.5 }}>
            Sources cited in an answer show up here.
          </p>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 9 }}>
            {sources.map((n) => (
              <SourceChip
                key={n}
                index={n}
                filename={`Source ${n}`}
                locator="cited in this answer"
                type="pdf"
                active={active === n}
                onClick={() => setActive(n)}
              />
            ))}
          </div>
        )}
        <div style={{ marginTop: 18 }}>
          <Alert tone="info" icon={<Icon name="helpCircle" size={16} />}>
            Click a <code>[N]</code> marker or a source to highlight where the answer came from.
          </Alert>
        </div>
      </aside>
    </div>
  );
}
