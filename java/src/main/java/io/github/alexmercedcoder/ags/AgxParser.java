package io.github.alexmercedcoder.ags;

import java.util.ArrayList;
import java.util.List;

/** Parser for the safe AGX expression grammar. */
public final class AgxParser {
  private AgxParser() {}

  /** A function call found in an expression. */
  public record Call(String name, int arity) {}
  /** Structural information collected from an expression. */
  public record Expression(List<Call> calls, List<List<String>> references) {}

  /** AGX syntax error. */
  public static final class AgxException extends Exception {
    private static final long serialVersionUID = 1L;
    AgxException(String message) { super(message); }
  }

  private enum Kind { NAME, VALUE, OP, LP, RP, LB, RB, DOT, COMMA }
  private record Token(Kind kind, String text) {}

  /** Parses valid AGX syntax and collects calls and dotted references. */
  public static Expression parse(String input) throws AgxException {
    Parser parser = new Parser(tokenize(input));
    parser.expression();
    if (parser.peek() != null) throw new AgxException("unexpected trailing token");
    return new Expression(List.copyOf(parser.calls), List.copyOf(parser.references));
  }

  private static List<Token> tokenize(String input) throws AgxException {
    List<Token> out = new ArrayList<>();
    int at = 0;
    while (at < input.length()) {
      char c = input.charAt(at);
      if (Character.isWhitespace(c)) { at++; continue; }
      Kind punctuation = switch (c) {
        case '(' -> Kind.LP; case ')' -> Kind.RP; case '[' -> Kind.LB; case ']' -> Kind.RB;
        case '.' -> Kind.DOT; case ',' -> Kind.COMMA; default -> null;
      };
      if (punctuation != null) { out.add(new Token(punctuation, Character.toString(c))); at++; continue; }
      if (c == '\'' || c == '"') {
        char quote = c; at++; boolean closed = false;
        while (at < input.length()) {
          if (input.charAt(at) == '\\') { at += 2; continue; }
          if (input.charAt(at++) == quote) { closed = true; break; }
        }
        if (!closed) throw new AgxException("unterminated string");
        out.add(new Token(Kind.VALUE, "string")); continue;
      }
      if (Character.isDigit(c)) {
        int start = at++;
        while (at < input.length() && "0123456789.eE+-".indexOf(input.charAt(at)) >= 0) at++;
        out.add(new Token(Kind.VALUE, input.substring(start, at))); continue;
      }
      if (Character.isLetter(c) || c == '_') {
        int start = at++;
        while (at < input.length() && (Character.isLetterOrDigit(input.charAt(at)) || input.charAt(at) == '_')) at++;
        String word = input.substring(start, at);
        if (List.of("true", "false", "null").contains(word)) out.add(new Token(Kind.VALUE, word));
        else if (word.equals("in")) out.add(new Token(Kind.OP, word));
        else out.add(new Token(Kind.NAME, word));
        continue;
      }
      String op = null;
      for (String candidate : List.of("&&", "||", "==", "!=", "<=", ">=", "+", "-", "*", "/", "%", "!", "<", ">")) {
        if (input.startsWith(candidate, at)) { op = candidate; break; }
      }
      if (op == null) throw new AgxException("unexpected character " + c);
      out.add(new Token(Kind.OP, op)); at += op.length();
    }
    return out;
  }

  private static final class Parser {
    private final List<Token> tokens;
    private int at;
    private final List<Call> calls = new ArrayList<>();
    private final List<List<String>> references = new ArrayList<>();
    Parser(List<Token> tokens) { this.tokens = tokens; }
    Token peek() { return at < tokens.size() ? tokens.get(at) : null; }
    Token take() throws AgxException { if (peek() == null) throw new AgxException("unexpected end of expression"); return tokens.get(at++); }
    boolean op(String wanted) { if (peek() != null && peek().kind == Kind.OP && peek().text.equals(wanted)) { at++; return true; } return false; }
    void expression() throws AgxException { or(); }
    void or() throws AgxException { and(); while (op("||")) and(); }
    void and() throws AgxException { equality(); while (op("&&")) equality(); }
    void equality() throws AgxException { comparison(); while (op("==") || op("!=") || op("in")) comparison(); }
    void comparison() throws AgxException { additive(); while (op("<") || op("<=") || op(">") || op(">=")) additive(); }
    void additive() throws AgxException { product(); while (op("+") || op("-")) product(); }
    void product() throws AgxException { unary(); while (op("*") || op("/") || op("%")) unary(); }
    void unary() throws AgxException { if (op("!") || op("-")) unary(); else primary(); }
    void primary() throws AgxException {
      Token token = take();
      if (token.kind == Kind.VALUE) return;
      if (token.kind == Kind.LP) { or(); if (take().kind != Kind.RP) throw new AgxException("expected ')'"); return; }
      if (token.kind == Kind.LB) {
        if (peek() != null && peek().kind == Kind.RB) { at++; return; }
        while (true) { or(); Token end = take(); if (end.kind == Kind.RB) return; if (end.kind != Kind.COMMA) throw new AgxException("expected ',' or ']'"); }
      }
      if (token.kind != Kind.NAME) throw new AgxException("expected expression");
      if (peek() != null && peek().kind == Kind.LP) {
        at++; int arity = 0;
        if (peek() == null || peek().kind != Kind.RP) {
          while (true) { or(); arity++; if (peek() != null && peek().kind == Kind.COMMA) at++; else break; }
        }
        if (take().kind != Kind.RP) throw new AgxException("expected ')'");
        calls.add(new Call(token.text, arity));
      } else {
        List<String> parts = new ArrayList<>(); parts.add(token.text);
        while (peek() != null && peek().kind == Kind.DOT) { at++; Token part = take(); if (part.kind != Kind.NAME) throw new AgxException("expected name after '.'"); parts.add(part.text); }
        references.add(List.copyOf(parts));
      }
    }
  }
}
