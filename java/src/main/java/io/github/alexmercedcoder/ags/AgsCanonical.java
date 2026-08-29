package io.github.alexmercedcoder.ags;

import com.fasterxml.jackson.databind.JsonNode;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.Base64;
import org.erdtman.jcs.JsonCanonicalizer;

/** RFC 8785 canonical JSON and AGS graph identities. */
public final class AgsCanonical {
  private AgsCanonical() {}

  /** Returns the RFC 8785 UTF-8 representation of a JSON value. */
  public static byte[] canonicalJson(JsonNode value) {
    try {
      return new JsonCanonicalizer(value.toString()).getEncodedUTF8();
    } catch (IOException error) {
      throw new IllegalArgumentException("canonical JSON error", error);
    }
  }

  /** Computes the AGS {@code sha256-<base64>} graph identity. */
  public static String graphDigest(JsonNode document) {
    try {
      byte[] digest = MessageDigest.getInstance("SHA-256").digest(canonicalJson(document));
      return "sha256-" + Base64.getEncoder().encodeToString(digest);
    } catch (NoSuchAlgorithmException impossible) {
      throw new IllegalStateException("SHA-256 is unavailable", impossible);
    }
  }
}
