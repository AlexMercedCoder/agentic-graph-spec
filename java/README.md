# Agentic Graph Specification for Java

Java 17 support for Agentic Graph Specification 1.0, at parity with the Python,
TypeScript, Go, and Rust Level 0 libraries. It provides strict YAML 1.2 and JSON
parsing, embedded schema and semantic validation, AGX parsing, RFC 8785 graph
identities, effective edges, deterministic topological ordering and planning,
and a validator CLI. It validates and plans graphs; it does not execute them.

Version 1.0.4 is available from [Maven Central](https://central.sonatype.com/artifact/io.github.alexmercedcoder/agentic-graph-spec/1.0.4).

```xml
<dependency>
  <groupId>io.github.alexmercedcoder</groupId>
  <artifactId>agentic-graph-spec</artifactId>
  <version>1.0.4</version>
</dependency>
```

```java
ObjectNode graph = AgsParser.load(Path.of("graph.agraph.yaml"));
Ags.ValidationReport report = AgsValidator.validate(graph);
if (!report.ok()) throw new IllegalArgumentException(report.errors().toString());
System.out.println(AgsCanonical.graphDigest(graph));
System.out.println(AgsPlanner.plan(graph).order());
```

Build and run the bundled executable JAR:

```console
JAVA_HOME=/path/to/jdk-17 mvn verify
java -jar target/agentic-graph-spec-1.0.4-cli.jar --strict ../examples/minimal.agraph.yaml
```

Maintainers can produce the complete Maven Central artifact set and GPG
signatures with `mvn -Prelease clean verify`. Publishing additionally requires
a Central Portal user token under server ID `central` in `~/.m2/settings.xml`;
use `mvn -Prelease clean deploy` to upload a manually reviewed deployment.
