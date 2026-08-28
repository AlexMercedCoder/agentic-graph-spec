use std::{path::PathBuf, process::ExitCode};

use agentic_graph_spec::validate_path;
use clap::Parser;

#[derive(Parser)]
#[command(version, about = "Validate Agentic Graph Specification documents")]
struct Arguments {
    /// Treat warnings as failures.
    #[arg(long)]
    strict: bool,
    /// Graph files to validate.
    #[arg(required = true)]
    paths: Vec<PathBuf>,
}

fn main() -> ExitCode {
    let arguments = Arguments::parse();
    let mut failed = false;
    for path in arguments.paths {
        let report = validate_path(&path);
        for finding in &report.findings {
            eprintln!(
                "[{}] {}: {}{}",
                finding.severity,
                finding.code,
                finding.message,
                if finding.pointer.is_empty() {
                    String::new()
                } else {
                    format!(" at {}", finding.pointer)
                }
            );
        }
        if !report.ok || (arguments.strict && !report.warnings.is_empty()) {
            failed = true;
        } else {
            println!("{}: valid", path.display());
        }
    }
    if failed {
        ExitCode::FAILURE
    } else {
        ExitCode::SUCCESS
    }
}
