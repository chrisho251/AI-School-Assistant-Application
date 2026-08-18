import { afterEach, describe, expect, it, vi } from 'vitest';

import { ApiClient, ApiError } from '@/lib/api';

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('ApiClient.request', () => {
  it('returns parsed JSON on 2xx and attaches the bearer token', async () => {
    const fetchMock = vi.fn((_url: string | URL, _init?: RequestInit): Promise<Response> =>
      Promise.resolve(jsonResponse([{ id: 'n1', title: 'Bio' }])),
    );
    vi.stubGlobal('fetch', fetchMock);

    const client = new ApiClient('dev.u.o.teacher');
    const notebooks = await client.listNotebooks();

    expect(notebooks).toEqual([{ id: 'n1', title: 'Bio' }]);
    const init = fetchMock.mock.calls[0][1];
    expect(init?.headers).toMatchObject({
      Authorization: 'Bearer dev.u.o.teacher',
    });
  });

  it('throws ApiError with the server detail on non-2xx', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => jsonResponse({ detail: 'Notebook not found' }, 404)),
    );
    const client = new ApiClient('t');
    await expect(client.getNotebook('missing')).rejects.toMatchObject({
      status: 404,
      detail: 'Notebook not found',
    });
    await expect(client.getNotebook('missing')).rejects.toBeInstanceOf(ApiError);
  });
});

describe('ApiClient.streamChat', () => {
  it('yields token events in order, stripping one leading space', async () => {
    const sse =
      'event: token\ndata: Hello\n\nevent: token\ndata:  world\n\nevent: done\ndata: \n\n';
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response(sse, { status: 200 })),
    );

    const client = new ApiClient('t');
    const tokens: string[] = [];
    for await (const tok of client.streamChat({ notebookId: 'n', question: 'q' })) {
      tokens.push(tok);
    }
    expect(tokens).toEqual(['Hello', ' world']);
  });

  it('throws ApiError on an error event', async () => {
    const sse = 'event: error\ndata: Boom\n\n';
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response(sse, { status: 200 })),
    );

    const client = new ApiClient('t');
    const consume = async () => {
      for await (const _tok of client.streamChat({ notebookId: 'n', question: 'q' })) {
        void _tok;
      }
    };
    await expect(consume()).rejects.toMatchObject({ status: 502, detail: 'Boom' });
  });
});
