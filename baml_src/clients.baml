// Present ONLY to satisfy ExtractDynamic's required `client` field. BAML is used
// parser-only here (b.parse.*), so this client is NEVER actually invoked — no
// LLM call is ever made from swe_af. The CLI harness providers own every model
// call. env.ANTHROPIC_API_KEY need not even be set for the parse path.
client<llm> AnthropicClient {
  provider anthropic
  options {
    model "claude-3-5-sonnet-20241022"
    api_key env.ANTHROPIC_API_KEY
  }
}
