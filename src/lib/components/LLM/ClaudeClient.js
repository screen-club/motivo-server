// ClaudeClient.js - Handler for Claude communication

import { processRewards } from "./utils.js";

/**
 * Creates a Claude client for handling Claude model communication
 */
export function createClaudeClient(
  chatStore,
  rewardStore,
  websocketService,
  uuidFn
) {
  const sendMessage = async (
    apiUrl,
    prompt,
    sessionId,
    addToExisting = false
  ) => {
    try {
      const res = await fetch(`${apiUrl}/generate-reward`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          prompt,
          sessionId,
          add_to_existing: addToExisting,
        }),
      });

      const data = await res.json();

      if (data.error) {
        throw new Error(data.error);
      }

      // Update chatStore for maintaining state
      chatStore.update((store) => ({
        ...store,
        sessionId: data.sessionId,
        response: data.reward_config,
        conversation: data.conversation,
      }));

      try {
        const rewardConfig = JSON.parse(data.reward_config);
        const addToExisting = data.add_to_existing === true;

        if (rewardConfig.rewards && Array.isArray(rewardConfig.rewards)) {
          // Enable batch mode for multiple rewards processing
          const hasMultipleRewards = rewardConfig.rewards.length > 1;

          processRewards(
            rewardConfig,
            rewardStore,
            websocketService,
            uuidFn,
            addToExisting
          );
        }
      } catch (e) {
        console.error("Error processing reward configuration", e);
      }

      return {
        conversation: data.conversation,
        success: true,
      };
    } catch (error) {
      console.error("Error in Claude API call", error);
      chatStore.update((store) => ({
        ...store,
        response: `Error: ${error.message}`,
      }));

      return {
        error: error.message,
        success: false,
      };
    }
  };

  const clearConversation = async (apiUrl, sessionId) => {
    try {
      const res = await fetch(`${apiUrl}/clear-chat`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ sessionId }),
      });

      if (!res.ok) throw new Error("Failed to clear chat");

      // Update the chatStore
      chatStore.update((store) => ({
        ...store,
        conversation: [],
        response: "",
      }));

      return true;
    } catch (error) {
      console.error("Error clearing Claude chat", error);
      return false;
    }
  };

  return {
    sendMessage,
    clearConversation,
  };
}
