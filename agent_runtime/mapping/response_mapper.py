def map_message_result(bot_result: dict) -> dict:
    response_data = {"reply": bot_result.get("reply") or bot_result.get("text", "")}

    if "current_flow" in bot_result:
        response_data["current_flow"] = bot_result["current_flow"]
    if "past_flows" in bot_result:
        response_data["past_flows"] = bot_result["past_flows"]
    if "future_flows" in bot_result:
        response_data["future_flows"] = bot_result["future_flows"]
    if "campaign_status" in bot_result:
        response_data["campaign_status"] = bot_result["campaign_status"]
    if "campaign_context" in bot_result:
        response_data["campaign_context"] = bot_result["campaign_context"]
    if "campaign_id" in bot_result:
        response_data["campaign_id"] = bot_result["campaign_id"]
    if "search_run_id" in bot_result:
        response_data["search_run_id"] = bot_result["search_run_id"]
    if "sequence_list" in bot_result:
        response_data["sequence_list"] = bot_result["sequence_list"]

    if "state" in bot_result:
        response_data["slots"] = bot_result.get("state", {}).get("slots", {})
    if "search_parameters" in bot_result:
        response_data["search_parameters"] = bot_result["search_parameters"]
    if "provider_metadata" in bot_result:
        response_data["provider_metadata"] = bot_result["provider_metadata"]
    if "next_action" in bot_result:
        response_data["next_action"] = bot_result["next_action"]

    return response_data
