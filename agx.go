package ags

import (
	"fmt"
	"strings"
	"unicode"
)

type Arity struct{ Min, Max int }

var AGXFunctions = map[string]Arity{"len": {1, 1}, "count": {1, 1}, "contains": {2, 2}, "startswith": {2, 2}, "endswith": {2, 2}, "lower": {1, 1}, "upper": {1, 1}, "trim": {1, 1}, "matches": {2, 2}, "split": {2, 2}, "join": {2, 2}, "int": {1, 1}, "float": {1, 1}, "bool": {1, 1}, "str": {1, 1}, "json": {1, 1}, "get": {2, 3}, "default": {2, 2}, "any": {1, 1}, "all": {1, 1}, "succeeded": {1, 1}, "failed": {1, 1}, "skipped": {1, 1}, "output": {2, 2}}

type Call struct {
	Name  string
	Arity int
}
type ParsedExpression struct {
	References [][]string
	Calls      []Call
}
type AgxSyntaxError struct{ Message string }

func (e *AgxSyntaxError) Error() string { return e.Message }

type token struct{ kind, value string }

func tokenizeExpression(input string) ([]token, error) {
	tokens := []token{}
	runes := []rune(input)
	for i := 0; i < len(runes); {
		if unicode.IsSpace(runes[i]) {
			i++
			continue
		}
		start := i
		current := runes[i]
		if unicode.IsDigit(current) || (current == '-' && i+1 < len(runes) && unicode.IsDigit(runes[i+1])) {
			i++
			for i < len(runes) && unicode.IsDigit(runes[i]) {
				i++
			}
			if i < len(runes) && runes[i] == '.' {
				i++
				for i < len(runes) && unicode.IsDigit(runes[i]) {
					i++
				}
			}
			tokens = append(tokens, token{"number", string(runes[start:i])})
			continue
		}
		if current == rune(39) || current == '"' {
			quote := current
			i++
			escaped := false
			for i < len(runes) {
				if escaped {
					escaped = false
					i++
					continue
				}
				if runes[i] == '\\' {
					escaped = true
					i++
					continue
				}
				if runes[i] == quote {
					i++
					tokens = append(tokens, token{"string", string(runes[start:i])})
					break
				}
				i++
			}
			if len(tokens) == 0 || tokens[len(tokens)-1].value != string(runes[start:i]) {
				return nil, &AgxSyntaxError{"unterminated string"}
			}
			continue
		}
		if unicode.IsLetter(current) || current == '_' {
			i++
			for i < len(runes) && (unicode.IsLetter(runes[i]) || unicode.IsDigit(runes[i]) || runes[i] == '_') {
				i++
			}
			tokens = append(tokens, token{"name", string(runes[start:i])})
			continue
		}
		operator := string(current)
		if i+1 < len(runes) {
			pair := string(runes[i : i+2])
			if pair == "&&" || pair == "||" || pair == "==" || pair == "!=" || pair == "<=" || pair == ">=" {
				operator = pair
				i++
			}
		}
		if !strings.Contains("-+*/%<>!()[],.", string(current)) && len(operator) == 1 {
			return nil, &AgxSyntaxError{fmt.Sprintf("unexpected character %q at offset %d", current, i)}
		}
		tokens = append(tokens, token{"op", operator})
		i++
	}
	return tokens, nil
}

type expressionParser struct {
	tokens   []token
	position int
	result   ParsedExpression
}

func ParseExpression(input string) (ParsedExpression, error) {
	tokens, err := tokenizeExpression(input)
	if err != nil {
		return ParsedExpression{}, err
	}
	parser := expressionParser{tokens: tokens}
	if err = parser.parseOr(); err != nil {
		return ParsedExpression{}, err
	}
	if parser.peek() != nil {
		return ParsedExpression{}, &AgxSyntaxError{fmt.Sprintf("trailing input at token %q", parser.peek().value)}
	}
	return parser.result, nil
}
func (p *expressionParser) peek() *token {
	if p.position >= len(p.tokens) {
		return nil
	}
	return &p.tokens[p.position]
}
func (p *expressionParser) take() (token, error) {
	if p.peek() == nil {
		return token{}, &AgxSyntaxError{"unexpected end of expression"}
	}
	result := p.tokens[p.position]
	p.position++
	return result, nil
}
func (p *expressionParser) match(kind, value string) bool {
	current := p.peek()
	if current != nil && current.kind == kind && current.value == value {
		p.position++
		return true
	}
	return false
}
func (p *expressionParser) expect(value string) error {
	current, err := p.take()
	if err != nil {
		return err
	}
	if current.kind != "op" || current.value != value {
		return &AgxSyntaxError{fmt.Sprintf("expected %q, found %q", value, current.value)}
	}
	return nil
}
func (p *expressionParser) parseOr() error {
	if err := p.parseAnd(); err != nil {
		return err
	}
	for p.match("op", "||") || p.match("name", "or") {
		if err := p.parseAnd(); err != nil {
			return err
		}
	}
	return nil
}
func (p *expressionParser) parseAnd() error {
	if err := p.parseIn(); err != nil {
		return err
	}
	for p.match("op", "&&") || p.match("name", "and") {
		if err := p.parseIn(); err != nil {
			return err
		}
	}
	return nil
}
func (p *expressionParser) parseIn() error {
	if err := p.parseEquality(); err != nil {
		return err
	}
	for p.match("name", "in") {
		if err := p.parseEquality(); err != nil {
			return err
		}
	}
	return nil
}
func (p *expressionParser) parseEquality() error {
	if err := p.parseComparison(); err != nil {
		return err
	}
	for p.match("op", "==") || p.match("op", "!=") {
		if err := p.parseComparison(); err != nil {
			return err
		}
	}
	return nil
}
func (p *expressionParser) parseComparison() error {
	if err := p.parseAdditive(); err != nil {
		return err
	}
	for {
		matched := false
		for _, op := range []string{"<=", ">=", "<", ">"} {
			if p.match("op", op) {
				matched = true
				break
			}
		}
		if !matched {
			return nil
		}
		if err := p.parseAdditive(); err != nil {
			return err
		}
	}
}
func (p *expressionParser) parseAdditive() error {
	if err := p.parseMultiplicative(); err != nil {
		return err
	}
	for p.match("op", "+") || p.match("op", "-") {
		if err := p.parseMultiplicative(); err != nil {
			return err
		}
	}
	return nil
}
func (p *expressionParser) parseMultiplicative() error {
	if err := p.parseUnary(); err != nil {
		return err
	}
	for {
		matched := false
		for _, op := range []string{"*", "/", "%"} {
			if p.match("op", op) {
				matched = true
				break
			}
		}
		if !matched {
			return nil
		}
		if err := p.parseUnary(); err != nil {
			return err
		}
	}
}
func (p *expressionParser) parseUnary() error {
	if p.match("op", "!") || p.match("op", "-") || p.match("name", "not") {
		return p.parseUnary()
	}
	return p.parsePrimary()
}
func (p *expressionParser) parsePrimary() error {
	current := p.peek()
	if current == nil {
		return &AgxSyntaxError{"unexpected end of expression"}
	}
	if current.kind == "number" || current.kind == "string" {
		p.position++
		return nil
	}
	if p.match("op", "(") {
		if err := p.parseOr(); err != nil {
			return err
		}
		return p.expect(")")
	}
	if p.match("op", "[") {
		if !p.match("op", "]") {
			if err := p.parseOr(); err != nil {
				return err
			}
			for p.match("op", ",") {
				if err := p.parseOr(); err != nil {
					return err
				}
			}
			return p.expect("]")
		}
		return nil
	}
	if current.kind != "name" {
		return &AgxSyntaxError{fmt.Sprintf("unexpected token %q", current.value)}
	}
	name := current.value
	p.position++
	if name == "true" || name == "false" || name == "null" {
		return nil
	}
	if name == "and" || name == "or" || name == "not" || name == "in" {
		return &AgxSyntaxError{fmt.Sprintf("unexpected keyword %q", name)}
	}
	if p.match("op", "(") {
		arity := 0
		if !p.match("op", ")") {
			if err := p.parseOr(); err != nil {
				return err
			}
			arity = 1
			for p.match("op", ",") {
				if err := p.parseOr(); err != nil {
					return err
				}
				arity++
			}
			if err := p.expect(")"); err != nil {
				return err
			}
		}
		p.result.Calls = append(p.result.Calls, Call{Name: name, Arity: arity})
		return nil
	}
	parts := []string{name}
	for p.match("op", ".") {
		segment, err := p.take()
		if err != nil {
			return err
		}
		if segment.kind != "name" {
			return &AgxSyntaxError{fmt.Sprintf("expected identifier after '.', found %q", segment.value)}
		}
		parts = append(parts, segment.value)
	}
	p.result.References = append(p.result.References, parts)
	return nil
}
