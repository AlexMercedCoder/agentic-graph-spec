package ags

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestConformanceCorpus(t *testing.T) {
	valid := []string{"minimal.agraph.yaml", "library-v1-release.agraph.yaml", "library-v1-release.agraph.json", "test-repair-loop.agraph.yaml", "docs-site-refresh.agraph.yaml", "link-audit.agraph.yaml"}
	for _, name := range valid {
		t.Run(name, func(t *testing.T) {
			report := ValidatePath(filepath.Join("examples", name))
			if !report.OK {
				t.Fatalf("unexpected errors: %+v", report.Errors)
			}
		})
	}
	entries, err := os.ReadDir(filepath.Join("conformance", "invalid"))
	if err != nil {
		t.Fatal(err)
	}
	for _, entry := range entries {
		name := entry.Name()
		if entry.IsDir() || !strings.HasSuffix(name, ".agraph.yaml") {
			continue
		}
		content, err := os.ReadFile(filepath.Join("conformance", "invalid", name))
		if err != nil {
			t.Fatal(err)
		}
		first := strings.SplitN(string(content), "\n", 2)[0]
		code := strings.TrimSpace(strings.TrimPrefix(first, "# EXPECT:"))
		if !strings.HasPrefix(first, "# EXPECT: AG") {
			t.Fatalf("%s has no EXPECT header", name)
		}
		t.Run(name, func(t *testing.T) {
			report := ValidatePath(filepath.Join("conformance", "invalid", name))
			found := false
			for _, finding := range report.Errors {
				if finding.Code == code {
					found = true
				}
			}
			if !found {
				t.Fatalf("wanted %s, got %+v", code, report.Errors)
			}
		})
	}
}

func TestDigestMatchesPythonAndTypeScript(t *testing.T) {
	document, err := Load("examples/library-v1-release.agraph.json")
	if err != nil {
		t.Fatal(err)
	}
	digest, err := GraphDigest(document)
	if err != nil {
		t.Fatal(err)
	}
	const expected = "sha256-ZaKZTS3i9OBDZNnKSNF2ZI22BZmOh1CcVNM0VZGDe+A="
	if digest != expected {
		t.Fatalf("got %s", digest)
	}
}

func TestYAML12AndDuplicates(t *testing.T) {
	document, err := Parse([]byte("value: yes\nenabled: true\ncreated: 2026-08-28T00:00:00Z\n"), "yaml")
	if err != nil {
		t.Fatal(err)
	}
	if document["value"] != "yes" || document["enabled"] != true || document["created"] != "2026-08-28T00:00:00Z" {
		t.Fatalf("unexpected parse: %#v", document)
	}
	if _, err := Parse([]byte("a: 1\na: 2\n"), "yaml"); err == nil {
		t.Fatal("expected duplicate rejection")
	}
	if _, err := Parse(nil, "yaml"); err == nil {
		t.Fatal("expected empty document rejection")
	}
}

func TestPlanIsDeterministic(t *testing.T) {
	document, err := Load("examples/minimal.agraph.yaml")
	if err != nil {
		t.Fatal(err)
	}
	first, err := PlanGraph(document)
	if err != nil {
		t.Fatal(err)
	}
	second, err := PlanGraph(document)
	if err != nil {
		t.Fatal(err)
	}
	if len(first.Order) != len(second.Order) {
		t.Fatal("different plans")
	}
	for i := range first.Order {
		if first.Order[i] != second.Order[i] {
			t.Fatal("different plans")
		}
	}
}

func TestAGXParser(t *testing.T) {
	parsed, err := ParseExpression("succeeded('build') && len(nodes.build.outputs.files) > 0")
	if err != nil {
		t.Fatal(err)
	}
	if len(parsed.Calls) != 2 || parsed.Calls[0].Name != "succeeded" || parsed.Calls[1].Arity != 1 {
		t.Fatalf("calls: %+v", parsed.Calls)
	}
	if len(parsed.References) != 1 || strings.Join(parsed.References[0], ".") != "nodes.build.outputs.files" {
		t.Fatalf("refs: %+v", parsed.References)
	}
}

func TestMain(m *testing.M) { os.Exit(m.Run()) }
