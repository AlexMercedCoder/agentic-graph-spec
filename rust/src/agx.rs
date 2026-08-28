use thiserror::Error;

/// A function call discovered while parsing an AGX expression.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct AgxCall {
    /// Function name.
    pub name: String,
    /// Number of supplied arguments.
    pub arity: usize,
}

/// Structural information collected from a valid AGX expression.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ParsedExpression {
    /// Function calls in encounter order.
    pub calls: Vec<AgxCall>,
    /// Dotted reference paths in encounter order.
    pub references: Vec<Vec<String>>,
}

/// Syntax error returned by the AGX parser.
#[derive(Debug, Error)]
#[error("{0}")]
pub struct AgxError(pub String);

#[derive(Debug, Clone, PartialEq, Eq)]
enum Token {
    Name(String),
    String,
    Number,
    True,
    False,
    Null,
    Op(String),
    LParen,
    RParen,
    LBracket,
    RBracket,
    Dot,
    Comma,
}

fn tokenize(input: &str) -> Result<Vec<Token>, AgxError> {
    let chars: Vec<char> = input.chars().collect();
    let mut tokens = vec![];
    let mut i = 0;
    while i < chars.len() {
        match chars[i] {
            c if c.is_whitespace() => i += 1,
            '(' => {
                tokens.push(Token::LParen);
                i += 1;
            }
            ')' => {
                tokens.push(Token::RParen);
                i += 1;
            }
            '[' => {
                tokens.push(Token::LBracket);
                i += 1;
            }
            ']' => {
                tokens.push(Token::RBracket);
                i += 1;
            }
            '.' => {
                tokens.push(Token::Dot);
                i += 1;
            }
            ',' => {
                tokens.push(Token::Comma);
                i += 1;
            }
            '\'' | '"' => {
                let quote = chars[i];
                i += 1;
                let mut closed = false;
                while i < chars.len() {
                    if chars[i] == '\\' {
                        i += 2;
                        continue;
                    }
                    if chars[i] == quote {
                        i += 1;
                        closed = true;
                        break;
                    }
                    i += 1;
                }
                if !closed {
                    return Err(AgxError("unterminated string".into()));
                }
                tokens.push(Token::String);
            }
            c if c.is_ascii_digit() => {
                i += 1;
                while i < chars.len()
                    && (chars[i].is_ascii_digit()
                        || matches!(chars[i], '.' | 'e' | 'E' | '+' | '-'))
                {
                    i += 1;
                }
                tokens.push(Token::Number);
            }
            c if c.is_ascii_alphabetic() || c == '_' => {
                let start = i;
                i += 1;
                while i < chars.len() && (chars[i].is_ascii_alphanumeric() || chars[i] == '_') {
                    i += 1;
                }
                let name: String = chars[start..i].iter().collect();
                tokens.push(match name.as_str() {
                    "true" => Token::True,
                    "false" => Token::False,
                    "null" => Token::Null,
                    "in" => Token::Op(name),
                    _ => Token::Name(name),
                });
            }
            _ => {
                let remaining: String = chars[i..].iter().collect();
                let op = [
                    "&&", "||", "==", "!=", "<=", ">=", "+", "-", "*", "/", "%", "!", "<", ">",
                ]
                .into_iter()
                .find(|candidate| remaining.starts_with(candidate))
                .ok_or_else(|| AgxError(format!("unexpected character {:?}", chars[i])))?;
                tokens.push(Token::Op(op.into()));
                i += op.len();
            }
        }
    }
    Ok(tokens)
}

struct Parser {
    tokens: Vec<Token>,
    at: usize,
    calls: Vec<AgxCall>,
    references: Vec<Vec<String>>,
}

impl Parser {
    fn peek(&self) -> Option<&Token> {
        self.tokens.get(self.at)
    }
    fn take(&mut self) -> Result<Token, AgxError> {
        let token = self
            .peek()
            .cloned()
            .ok_or_else(|| AgxError("unexpected end of expression".into()))?;
        self.at += 1;
        Ok(token)
    }
    fn op(&mut self, wanted: &str) -> bool {
        if matches!(self.peek(), Some(Token::Op(op)) if op == wanted) {
            self.at += 1;
            true
        } else {
            false
        }
    }
    fn parse(&mut self) -> Result<(), AgxError> {
        self.or()?;
        if self.peek().is_some() {
            return Err(AgxError("unexpected trailing token".into()));
        }
        Ok(())
    }
    fn or(&mut self) -> Result<(), AgxError> {
        self.and()?;
        while self.op("||") {
            self.and()?;
        }
        Ok(())
    }
    fn and(&mut self) -> Result<(), AgxError> {
        self.equality()?;
        while self.op("&&") {
            self.equality()?;
        }
        Ok(())
    }
    fn equality(&mut self) -> Result<(), AgxError> {
        self.comparison()?;
        loop {
            if self.op("==") || self.op("!=") || self.op("in") {
                self.comparison()?;
            } else {
                break;
            }
        }
        Ok(())
    }
    fn comparison(&mut self) -> Result<(), AgxError> {
        self.additive()?;
        loop {
            if self.op("<") || self.op("<=") || self.op(">") || self.op(">=") {
                self.additive()?;
            } else {
                break;
            }
        }
        Ok(())
    }
    fn additive(&mut self) -> Result<(), AgxError> {
        self.product()?;
        loop {
            if self.op("+") || self.op("-") {
                self.product()?;
            } else {
                break;
            }
        }
        Ok(())
    }
    fn product(&mut self) -> Result<(), AgxError> {
        self.unary()?;
        loop {
            if self.op("*") || self.op("/") || self.op("%") {
                self.unary()?;
            } else {
                break;
            }
        }
        Ok(())
    }
    fn unary(&mut self) -> Result<(), AgxError> {
        if self.op("!") || self.op("-") {
            self.unary()
        } else {
            self.primary()
        }
    }
    fn primary(&mut self) -> Result<(), AgxError> {
        match self.take()? {
            Token::String | Token::Number | Token::True | Token::False | Token::Null => Ok(()),
            Token::LParen => {
                self.or()?;
                if self.take()? != Token::RParen {
                    return Err(AgxError("expected ')'".into()));
                }
                Ok(())
            }
            Token::LBracket => {
                if matches!(self.peek(), Some(Token::RBracket)) {
                    self.at += 1;
                    return Ok(());
                }
                loop {
                    self.or()?;
                    match self.take()? {
                        Token::Comma => continue,
                        Token::RBracket => break,
                        _ => return Err(AgxError("expected ',' or ']'".into())),
                    }
                }
                Ok(())
            }
            Token::Name(name) => {
                if matches!(self.peek(), Some(Token::LParen)) {
                    self.at += 1;
                    let mut arity = 0;
                    if !matches!(self.peek(), Some(Token::RParen)) {
                        loop {
                            self.or()?;
                            arity += 1;
                            if matches!(self.peek(), Some(Token::Comma)) {
                                self.at += 1;
                            } else {
                                break;
                            }
                        }
                    }
                    if self.take()? != Token::RParen {
                        return Err(AgxError("expected ')'".into()));
                    }
                    self.calls.push(AgxCall { name, arity });
                } else {
                    let mut reference = vec![name];
                    while matches!(self.peek(), Some(Token::Dot)) {
                        self.at += 1;
                        match self.take()? {
                            Token::Name(part) => reference.push(part),
                            _ => return Err(AgxError("expected name after '.'".into())),
                        }
                    }
                    self.references.push(reference);
                }
                Ok(())
            }
            _ => Err(AgxError("expected expression".into())),
        }
    }
}

/// Parses and validates AGX syntax while collecting calls and references.
pub fn parse_expression(input: &str) -> Result<ParsedExpression, AgxError> {
    let mut parser = Parser {
        tokens: tokenize(input)?,
        at: 0,
        calls: vec![],
        references: vec![],
    };
    parser.parse()?;
    Ok(ParsedExpression {
        calls: parser.calls,
        references: parser.references,
    })
}
