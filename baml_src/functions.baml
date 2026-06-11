// The load-bearing dynamic pieces. DynamicOutput has NO static fields; its shape
// is supplied at call time via TypeBuilder (swe_af/baml_bridge.pydantic_to_typebuilder),
// letting one BAML function parse any runtime SWE-AF schema.
class DynamicOutput {
  @@dynamic
}

function ExtractDynamic(prompt: string) -> DynamicOutput {
  client AnthropicClient
  prompt #"
    {{ prompt }}

    {{ ctx.output_format }}
  "#
}
