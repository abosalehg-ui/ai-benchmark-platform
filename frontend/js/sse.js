/* محلّل Server-Sent Events — كان مدفوناً داخل حلقة الواجهة في runBenchmark. */

/**
 * يقرأ بثّ SSE من ReadableStreamDefaultReader ويُنتج {event, data}.
 * @param {ReadableStreamDefaultReader<Uint8Array>} reader
 */
export async function* readSSE(reader) {
  const decoder = new TextDecoder('utf-8');
  let buffer = '';

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    const blocks = buffer.split('\n\n');
    buffer = blocks.pop() || '';

    for (const block of blocks) {
      let type = '';
      let raw = '';
      for (const line of block.split('\n')) {
        if (line.startsWith('event:')) type = line.slice(6).trim();
        else if (line.startsWith('data:')) raw = line.slice(5).trim();
      }
      if (!type || !raw) continue;
      let data;
      try {
        data = JSON.parse(raw);
      } catch {
        continue; // حزمة تالفة — نتجاهلها بدل إسقاط البثّ كاملاً
      }
      yield { event: type, data };
    }
  }
}
