package ags

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strconv"
	"strings"

	"gopkg.in/yaml.v3"
)

type ParseError struct {
	Code string
	Err  error
}

func (e *ParseError) Error() string { return e.Err.Error() }
func (e *ParseError) Unwrap() error { return e.Err }

func Parse(data []byte, format string) (Document, error) {
	var value any
	if strings.EqualFold(format, "json") {
		decoder := json.NewDecoder(bytes.NewReader(data))
		decoder.UseNumber()
		if err := decoder.Decode(&value); err != nil {
			return nil, &ParseError{Code: "AG001", Err: fmt.Errorf("parse error: %w", err)}
		}
		if err := decoder.Decode(new(any)); err != io.EOF {
			return nil, &ParseError{Code: "AG001", Err: fmt.Errorf("parse error: trailing JSON value")}
		}
	} else {
		var root yaml.Node
		if err := yaml.Unmarshal(data, &root); err != nil {
			code := "AG001"
			if strings.Contains(strings.ToLower(err.Error()), "already defined") {
				code = "AG005"
			}
			return nil, &ParseError{Code: code, Err: fmt.Errorf("parse error: %w", err)}
		}
		if len(root.Content) == 0 {
			return nil, &ParseError{Code: "AG001", Err: fmt.Errorf("parse error: empty document")}
		}
		converted, err := yamlValue(root.Content[0])
		if err != nil {
			return nil, err
		}
		value = converted
	}
	document, ok := value.(map[string]any)
	if !ok {
		return nil, &ParseError{Code: "AG001", Err: fmt.Errorf("document root must be an object")}
	}
	return Document(document), nil
}

func Load(path string) (Document, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	format := "yaml"
	if strings.EqualFold(filepath.Ext(path), ".json") {
		format = "json"
	}
	return Parse(data, format)
}

func yamlValue(node *yaml.Node) (any, error) {
	switch node.Kind {
	case yaml.MappingNode:
		result := map[string]any{}
		for i := 0; i < len(node.Content); i += 2 {
			key := node.Content[i].Value
			if _, exists := result[key]; exists {
				return nil, &ParseError{Code: "AG005", Err: fmt.Errorf("duplicate key %q", key)}
			}
			value, err := yamlValue(node.Content[i+1])
			if err != nil {
				return nil, err
			}
			result[key] = value
		}
		return result, nil
	case yaml.SequenceNode:
		result := make([]any, len(node.Content))
		for i, child := range node.Content {
			value, err := yamlValue(child)
			if err != nil {
				return nil, err
			}
			result[i] = value
		}
		return result, nil
	case yaml.ScalarNode:
		switch node.Tag {
		case "!!null":
			return nil, nil
		case "!!bool":
			return node.Value == "true", nil
		case "!!int":
			value, err := strconv.ParseInt(node.Value, 0, 64)
			if err != nil {
				return nil, err
			}
			return value, nil
		case "!!float":
			value, err := strconv.ParseFloat(node.Value, 64)
			if err != nil {
				return nil, err
			}
			return value, nil
		default:
			return node.Value, nil
		}
	default:
		return nil, fmt.Errorf("unsupported YAML node kind %d", node.Kind)
	}
}

func ValidatePath(path string) Report {
	document, err := Load(path)
	if err != nil {
		code := "AG001"
		if parse, ok := err.(*ParseError); ok {
			code = parse.Code
		}
		report := Report{}
		report.add(code, "error", err.Error(), "")
		return report
	}
	return Validate(document)
}
