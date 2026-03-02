type CompletePredicate<T> = (event: T) => boolean;
type ResultExtractor<T, R> = (event: T) => R;

type WaitingResolver<T> = {
  resolve: (value: IteratorResult<T>) => void;
};

export class EventStream<T, R = T> implements AsyncIterable<T> {
  private readonly isComplete: CompletePredicate<T>;
  private readonly extractResult: ResultExtractor<T, R>;
  private readonly queue: T[] = [];
  private readonly waiting: WaitingResolver<T>[] = [];
  private ended = false;
  private finalResult: R | null = null;
  private finalResultResolver: ((value: R) => void) | null = null;
  private finalResultPromise: Promise<R>;

  constructor(isComplete: CompletePredicate<T>, extractResult: ResultExtractor<T, R>) {
    this.isComplete = isComplete;
    this.extractResult = extractResult;
    this.finalResultPromise = new Promise<R>((resolve) => {
      this.finalResultResolver = resolve;
    });
  }

  push(event: T): void {
    if (this.ended) {
      return;
    }
    this.queue.push(event);
    const waiter = this.waiting.shift();
    if (waiter) {
      const value = this.queue.shift();
      if (value !== undefined) {
        waiter.resolve({ value, done: false });
      } else {
        waiter.resolve({ value: undefined as T, done: true });
      }
    }
    if (this.isComplete(event)) {
      this.end(this.extractResult(event));
    }
  }

  end(result?: R): void {
    if (this.ended) {
      return;
    }
    this.ended = true;
    if (result !== undefined) {
      this.finalResult = result;
    }
    if (this.finalResultResolver) {
      this.finalResultResolver((this.finalResult ?? (undefined as R)) as R);
      this.finalResultResolver = null;
    }
    while (this.waiting.length > 0) {
      const waiter = this.waiting.shift();
      waiter?.resolve({ value: undefined as T, done: true });
    }
  }

  [Symbol.asyncIterator](): AsyncIterator<T> {
    return {
      next: async (): Promise<IteratorResult<T>> => {
        if (this.queue.length > 0) {
          const value = this.queue.shift() as T;
          return { value, done: false };
        }
        if (this.ended) {
          return { value: undefined as T, done: true };
        }
        return new Promise<IteratorResult<T>>((resolve) => {
          this.waiting.push({ resolve });
        });
      }
    };
  }

  result(): Promise<R> {
    return this.finalResultPromise;
  }
}

export function parseStreamingJson(value: string): Record<string, unknown> | null {
  try {
    const parsed = JSON.parse(value);
    if (typeof parsed === "object" && parsed !== null) {
      return parsed as Record<string, unknown>;
    }
  } catch {
    // partial JSON chunks are expected while streaming tool-call arguments
  }
  return null;
}

export function validateToolArguments(_toolOrSchema: unknown, toolCallOrArgs: unknown): unknown {
  if (
    toolCallOrArgs &&
    typeof toolCallOrArgs === "object" &&
    "arguments" in (toolCallOrArgs as Record<string, unknown>)
  ) {
    const rawArgs = (toolCallOrArgs as { arguments?: unknown }).arguments;
    if (typeof rawArgs === "string") {
      return parseStreamingJson(rawArgs) ?? {};
    }
    return rawArgs ?? {};
  }
  return toolCallOrArgs;
}

export function streamSimple(): never {
  throw new Error("streamSimple is unavailable in browser shim; provide streamFn");
}

export function getModel(provider: string, modelId: string): Record<string, unknown> {
  return {
    id: modelId,
    name: modelId,
    provider,
    api: "openai-completions",
    baseUrl: ""
  };
}
