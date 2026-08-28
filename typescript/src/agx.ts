export const AGX_FUNCTIONS: Readonly<Record<string, number | readonly [number, number]>> = {
  len: 1,
  count: 1,
  contains: 2,
  startswith: 2,
  endswith: 2,
  lower: 1,
  upper: 1,
  trim: 1,
  matches: 2,
  split: 2,
  join: 2,
  int: 1,
  float: 1,
  bool: 1,
  str: 1,
  json: 1,
  get: [2, 3],
  default: 2,
  any: 1,
  all: 1,
  succeeded: 1,
  failed: 1,
  skipped: 1,
  output: 2,
};

type TokenKind = "number" | "string" | "op" | "name";
type Token = readonly [TokenKind, string];

export interface ParsedExpression {
  references: string[][];
  calls: Array<{ name: string; arity: number }>;
}

export class AgxSyntaxError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "AgxSyntaxError";
  }
}

const tokenPattern = /\s*(?:(?<number>-?\d+\.\d+|-?\d+)|(?<string>"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')|(?<op>&&|\|\||==|!=|<=|>=|[-+*/%<>!()\[\],.])|(?<name>[A-Za-z_][A-Za-z0-9_]*))/y;

function tokenize(text: string): Token[] {
  const tokens: Token[] = [];
  let index = 0;
  while (index < text.length) {
    if (/\s/.test(text[index] ?? "")) {
      index += 1;
      continue;
    }
    tokenPattern.lastIndex = index;
    const match = tokenPattern.exec(text);
    if (!match || match.index !== index || !match.groups) {
      throw new AgxSyntaxError(`unexpected character ${JSON.stringify(text[index])} at offset ${index}`);
    }
    index = tokenPattern.lastIndex;
    for (const kind of ["number", "string", "op", "name"] as const) {
      const value = match.groups[kind];
      if (value !== undefined) {
        tokens.push([kind, value]);
        break;
      }
    }
  }
  return tokens;
}

class Parser {
  private readonly tokens: Token[];
  private position = 0;
  readonly references: string[][] = [];
  readonly calls: Array<{ name: string; arity: number }> = [];

  constructor(text: string) {
    this.tokens = tokenize(text);
  }

  parse(): ParsedExpression {
    this.parseOr();
    const trailing = this.peek();
    if (trailing) throw new AgxSyntaxError(`trailing input at token ${JSON.stringify(trailing[1])}`);
    return { references: this.references, calls: this.calls };
  }

  private peek(): Token | undefined {
    return this.tokens[this.position];
  }

  private take(): Token {
    const token = this.tokens[this.position];
    if (!token) throw new AgxSyntaxError("unexpected end of expression");
    this.position += 1;
    return token;
  }

  private match(kind: TokenKind, value: string): boolean {
    const token = this.peek();
    if (token?.[0] === kind && token[1] === value) {
      this.position += 1;
      return true;
    }
    return false;
  }

  private expectOp(value: string): void {
    const token = this.take();
    if (token[0] !== "op" || token[1] !== value) {
      throw new AgxSyntaxError(`expected ${JSON.stringify(value)}, found ${JSON.stringify(token[1])}`);
    }
  }

  private parseOr(): void {
    this.parseAnd();
    while (this.match("op", "||") || this.match("name", "or")) this.parseAnd();
  }

  private parseAnd(): void {
    this.parseIn();
    while (this.match("op", "&&") || this.match("name", "and")) this.parseIn();
  }

  private parseIn(): void {
    this.parseEquality();
    while (this.match("name", "in")) this.parseEquality();
  }

  private parseEquality(): void {
    this.parseComparison();
    while (this.match("op", "==") || this.match("op", "!=")) this.parseComparison();
  }

  private parseComparison(): void {
    this.parseAdditive();
    while (["<=", ">=", "<", ">"].some((operator) => this.match("op", operator))) {
      this.parseAdditive();
    }
  }

  private parseAdditive(): void {
    this.parseMultiplicative();
    while (this.match("op", "+") || this.match("op", "-")) this.parseMultiplicative();
  }

  private parseMultiplicative(): void {
    this.parseUnary();
    while (["*", "/", "%"].some((operator) => this.match("op", operator))) this.parseUnary();
  }

  private parseUnary(): void {
    if (this.match("op", "!") || this.match("op", "-") || this.match("name", "not")) {
      this.parseUnary();
      return;
    }
    this.parsePrimary();
  }

  private parsePrimary(): void {
    const token = this.peek();
    if (!token) throw new AgxSyntaxError("unexpected end of expression");
    if (token[0] === "number" || token[0] === "string") {
      this.take();
      return;
    }
    if (this.match("op", "(")) {
      this.parseOr();
      this.expectOp(")");
      return;
    }
    if (this.match("op", "[")) {
      if (!this.match("op", "]")) {
        this.parseOr();
        while (this.match("op", ",")) this.parseOr();
        this.expectOp("]");
      }
      return;
    }
    if (token[0] !== "name") throw new AgxSyntaxError(`unexpected token ${JSON.stringify(token[1])}`);
    const [, name] = this.take();
    if (["true", "false", "null"].includes(name)) return;
    if (["and", "or", "not", "in"].includes(name)) {
      throw new AgxSyntaxError(`unexpected keyword ${JSON.stringify(name)}`);
    }
    if (this.match("op", "(")) {
      let arity = 0;
      if (!this.match("op", ")")) {
        this.parseOr();
        arity = 1;
        while (this.match("op", ",")) {
          this.parseOr();
          arity += 1;
        }
        this.expectOp(")");
      }
      this.calls.push({ name, arity });
      return;
    }
    const parts = [name];
    while (this.match("op", ".")) {
      const segment = this.take();
      if (segment[0] !== "name") {
        throw new AgxSyntaxError(`expected identifier after '.', found ${JSON.stringify(segment[1])}`);
      }
      parts.push(segment[1]);
    }
    this.references.push(parts);
  }
}

export function parseExpression(text: string): ParsedExpression {
  return new Parser(text).parse();
}
