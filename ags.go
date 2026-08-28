// Package ags parses, validates, identifies, and plans Agentic Graph
// Specification 1.0 documents.
package ags

const (
	AGSVersion     = "1.0"
	SupportVersion = "1.0.2"
)

type Document map[string]any

type Finding struct {
	Code     string `json:"code"`
	Severity string `json:"severity"`
	Message  string `json:"message"`
	Pointer  string `json:"pointer,omitempty"`
}

type Report struct {
	Document Document  `json:"document,omitempty"`
	Findings []Finding `json:"findings"`
	Errors   []Finding `json:"errors"`
	Warnings []Finding `json:"warnings"`
	OK       bool      `json:"ok"`
}

func (r *Report) add(code, severity, message, pointer string) {
	f := Finding{Code: code, Severity: severity, Message: message, Pointer: pointer}
	r.Findings = append(r.Findings, f)
	if severity == "error" {
		r.Errors = append(r.Errors, f)
	} else {
		r.Warnings = append(r.Warnings, f)
	}
}

type EffectiveEdge struct {
	From string `json:"from"`
	To   string `json:"to"`
	Kind string `json:"kind"`
	When string `json:"when,omitempty"`
}

type Plan struct {
	GraphID                 string          `json:"graph_id"`
	GraphDigest             string          `json:"graph_digest"`
	Order                   []string        `json:"order"`
	Entrypoints             []string        `json:"entrypoints"`
	EffectiveEdges          []EffectiveEdge `json:"effective_edges"`
	Reachable               []string        `json:"reachable"`
	Unreachable             []string        `json:"unreachable"`
	TierHistogram           map[string]int  `json:"tier_histogram"`
	WorstCaseNodeExecutions int             `json:"worst_case_node_executions"`
	Executable              bool            `json:"executable"`
	UnsupportedFeatures     []string        `json:"unsupported_features"`
}
