package main

import (
	"flag"
	"fmt"
	"os"

	ags "github.com/AlexMercedCoder/agentic-graph-spec"
)

func main() {
	strict := flag.Bool("strict", false, "treat warnings as failures")
	flag.Parse()
	if flag.NArg() == 0 {
		fmt.Fprintln(os.Stderr, "usage: ags-validate [--strict] <graph> [...]")
		os.Exit(2)
	}
	failed := false
	for _, path := range flag.Args() {
		report := ags.ValidatePath(path)
		for _, finding := range report.Findings {
			fmt.Fprintf(os.Stderr, "[%s] %s: %s", finding.Severity, finding.Code, finding.Message)
			if finding.Pointer != "" {
				fmt.Fprintf(os.Stderr, " at %s", finding.Pointer)
			}
			fmt.Fprintln(os.Stderr)
		}
		if !report.OK || (*strict && len(report.Warnings) > 0) {
			failed = true
		} else {
			fmt.Printf("%s: valid\n", path)
		}
	}
	if failed {
		os.Exit(1)
	}
}
