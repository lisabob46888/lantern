// One WebSocket to /api/v1/stream. Reconnects with backoff and resumes from the last seq;
// on "resync" (gap older than the server's replay buffer) it asks the app to refetch snapshots.
import { useLive } from './live';
import type { Quote, WireEvent } from '@/lib/types';

type Msg = { seq?: number; ch?: string; type: string; data?: unknown };

let ws: WebSocket | null = null;
let retry = 0;
let channels = new Set<string>(['wire', 'quotes', 'report:*', 'industry']);
let onResync: () => void = () => {};

export function setResyncHandler(fn: () => void) {
  onResync = fn;
}

export function subscribe(chs: string[]) {
  chs.forEach((c) => channels.add(c));
  if (ws?.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ op: 'sub', channels: chs }));
}

function handle(m: Msg) {
  const live = useLive.getState();
  if (m.seq) live.setSeq(m.seq);
  switch (m.type) {
    case 'quotes':
      live.mergeQuotes(m.data as Record<string, Quote>);
      break;
    case 'event':
    case 'event_update':
      live.upsertEvent(m.data as WireEvent);
      break;
    case 'event_hide':
      live.hideEvent((m.data as WireEvent).id);
      break;
    case 'story_read':
    case 'story_failed':
      live.bumpStory((m.data as { id: string }).id);
      break;
    case 'postmarket':
      live.bumpReport();
      break;
    case 'industry_pack':
      live.bumpReport();
      break;
    case 'resync':
      onResync();
      break;
  }
}

export function connect() {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  ws = new WebSocket(`${proto}://${location.host}/api/v1/stream`);
  ws.onopen = () => {
    retry = 0;
    useLive.getState().setConnected(true);
    ws!.send(JSON.stringify({ op: 'sub', channels: [...channels], after: useLive.getState().lastSeq }));
  };
  ws.onmessage = (ev) => {
    try {
      handle(JSON.parse(ev.data));
    } catch {
      /* ignore malformed frame */
    }
  };
  ws.onclose = () => {
    useLive.getState().setConnected(false);
    const delay = Math.min(15000, 500 * 2 ** retry++);
    setTimeout(connect, delay);
  };
  ws.onerror = () => ws?.close();
}

export function resetChannels() {
  channels = new Set(['wire', 'quotes', 'report:*', 'industry']);
}
