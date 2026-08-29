package io.github.alexmercedcoder.ags;

import java.nio.file.Path;
import java.util.List;
import java.util.concurrent.Callable;
import picocli.CommandLine;
import picocli.CommandLine.Command;
import picocli.CommandLine.Option;
import picocli.CommandLine.Parameters;

/** Command-line AGS document validator. */
@Command(name = "ags-validate", mixinStandardHelpOptions = true, version = Ags.SUPPORT_VERSION,
    description = "Validate Agentic Graph Specification documents")
public final class AgsValidateCli implements Callable<Integer> {
  @Parameters(arity = "1..*", paramLabel = "PATH", description = "Graph files to validate")
  private List<Path> paths;

  @Option(names = "--strict", description = "Treat warnings as failures")
  private boolean strict;

  @Override public Integer call() {
    boolean failed = false;
    for (Path path : paths) {
      Ags.ValidationReport report = AgsValidator.validate(path);
      if (report.ok()) System.out.println(path + ": valid");
      for (Ags.Finding finding : report.findings()) {
        System.err.printf("%s: %s %s %s%s%n", path, finding.severity(), finding.code(), finding.message(),
            finding.pointer().isEmpty() ? "" : " at " + finding.pointer());
      }
      failed |= !report.ok() || (strict && !report.warnings().isEmpty());
    }
    return failed ? 1 : 0;
  }

  /** Runs the validator CLI. */
  public static void main(String[] args) {
    System.exit(new CommandLine(new AgsValidateCli()).execute(args));
  }
}
