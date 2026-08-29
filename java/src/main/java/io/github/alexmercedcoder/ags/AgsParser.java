package io.github.alexmercedcoder.ags;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Locale;

/** Strict JSON/YAML parsing for AGS documents. */
public final class AgsParser {
  private AgsParser() {}

  /** Parsing failure with its stable AGS diagnostic code. */
  public static final class ParseException extends Exception {
    private static final long serialVersionUID = 1L;
    private final String code;

    ParseException(String code, String message, Throwable cause) {
      super(message, cause);
      this.code = code;
    }

    /** Returns AG001 for general parsing errors or AG005 for duplicate keys. */
    public String code() { return code; }
  }

  /** Parses a JSON or YAML AGS document with duplicate-key rejection. */
  public static ObjectNode parse(String input, String format) throws ParseException {
    if (input == null || input.trim().isEmpty()) {
      throw new ParseException("AG001", "parse error: empty document", null);
    }
    try {
      JsonNode node = "json".equalsIgnoreCase(format)
          ? JsonSupport.JSON.readTree(input) : JsonSupport.parseYaml(input);
      if (node == null || !node.isObject()) {
        throw new ParseException("AG001", "document root must be an object", null);
      }
      return (ObjectNode) node;
    } catch (ParseException error) {
      throw error;
    } catch (IOException | RuntimeException error) {
      String message = error.getMessage() == null ? error.toString() : error.getMessage();
      String code = message.toLowerCase(Locale.ROOT).contains("duplicate") ? "AG005" : "AG001";
      throw new ParseException(code, "parse error: " + message, error);
    }
  }

  /** Loads an AGS document, selecting JSON for a {@code .json} path and YAML otherwise. */
  public static ObjectNode load(Path path) throws ParseException {
    try {
      String input = Files.readString(path, StandardCharsets.UTF_8);
      String format = path.toString().toLowerCase(Locale.ROOT).endsWith(".json") ? "json" : "yaml";
      return parse(input, format);
    } catch (IOException error) {
      throw new ParseException("AG001", error.getMessage(), error);
    }
  }
}
