package io.github.alexmercedcoder.ags;

import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.JsonNodeFactory;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.util.ArrayList;
import java.util.List;
import org.snakeyaml.engine.v2.api.Load;
import org.snakeyaml.engine.v2.api.LoadSettings;
import org.snakeyaml.engine.v2.schema.JsonSchema;

final class JsonSupport {
  static final ObjectMapper JSON = new ObjectMapper().enable(DeserializationFeature.USE_BIG_DECIMAL_FOR_FLOATS);
  static {
    JSON.enable(JsonParser.Feature.STRICT_DUPLICATE_DETECTION);
  }

  private JsonSupport() {}

  static ObjectNode emptyObject() {
    return JsonNodeFactory.instance.objectNode();
  }

  static List<String> strings(JsonNode node) {
    List<String> values = new ArrayList<>();
    if (node != null && node.isArray()) {
      node.forEach(value -> { if (value.isTextual()) values.add(value.textValue()); });
    }
    return values;
  }

  static JsonNode parseYaml(String input) {
    LoadSettings settings = LoadSettings.builder()
        .setAllowDuplicateKeys(false)
        .setAllowRecursiveKeys(false)
        .setAllowNonScalarKeys(false)
        .setSchema(new JsonSchema())
        .build();
    return JSON.valueToTree(new Load(settings).loadFromString(input));
  }
}
