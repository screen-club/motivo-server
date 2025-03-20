// utils.js - Helper functions for LLM component

/**
 * Extracts structured data from LLM response content
 */
export function extractStructuredResponse(content) {
  try {
    // First try to see if the entire content is valid JSON
    try {
      const directJson = JSON.parse(content);
      if (directJson && directJson.response) {
        return {
          response: content,
          explanation: directJson.response,
          result: directJson.result,
        };
      }
    } catch (e) {
      // Not direct JSON, continue with other extraction methods
    }

    // Create structure
    let structured = {
      response: content, // Full response text
      explanation: "", // Extracted explanation
      result: null, // Extracted rewards JSON
    };

    // Try to extract JSON from code blocks or content
    const jsonRegex =
      /```(?:json)?\s*(\{[\s\S]*?\})\s*```|`(\{[\s\S]*?\})`|(\{[\s\S]*?\})/g;
    const matches = [...content.matchAll(jsonRegex)];

    if (matches.length > 0) {
      // Find the first match that contains valid JSON
      for (const match of matches) {
        const jsonString = (match[1] || match[2] || match[3]).trim();
        try {
          const parsedJson = JSON.parse(jsonString);

          // If we find response field, use it directly
          if (parsedJson.response) {
            structured.explanation = parsedJson.response;
            structured.result = parsedJson.result;
            break;
          } else {
            // Otherwise store the whole JSON as the result
            structured.result = parsedJson;
          }
        } catch (e) {
          // Skip invalid JSON
          continue;
        }
      }
    }

    // If we still don't have an explanation, extract from text
    if (!structured.explanation) {
      // Extract explanation (all text before the first code block)
      if (matches.length > 0) {
        const firstMatchIndex = content.indexOf("```");
        if (firstMatchIndex > 0) {
          structured.explanation = content.substring(0, firstMatchIndex).trim();
        }
      } else {
        // If no code block, use all content as explanation
        structured.explanation = content;
      }
    }

    return structured;
  } catch (error) {
    console.error("Error extracting structured response", error);
    return {
      response: content,
      explanation: content,
      result: null,
    };
  }
}

/**
 * Process rewards from the LLM response
 */
export function processRewards(
  rewardData,
  rewardStore,
  websocketService,
  uuidFn,
  addToExisting = false
) {
  try {
    // Handle both direct reward objects and objects containing a rewards array
    const rewardConfig =
      typeof rewardData === "string" ? JSON.parse(rewardData) : rewardData;

    // Check if we have valid rewards data
    if (rewardConfig) {
      const rewardsArray =
        rewardConfig.rewards ||
        (Array.isArray(rewardConfig) ? rewardConfig : null);
      const weights = rewardConfig.weights || [];
      const combinationType = rewardConfig.combinationType || "geometric";

      if (rewardsArray && Array.isArray(rewardsArray)) {
        // Only clear rewards if we're not adding to existing ones and it's not an auto-capture
        const isAutoCaptureReward = rewardsArray.some(r => r.auto_capture === true);
        
        if (!addToExisting && !isAutoCaptureReward) {
          console.log("Clearing existing rewards before adding new ones");
          // Use websocketService.send which now handles queuing
          websocketService.send({
            type: "clear_active_rewards",
            preserve_z: false
          });

          rewardStore.cleanRewardsLocal();
        } else if (isAutoCaptureReward) {
          console.log("Auto-capture reward detected - preserving environment while clearing reward array");
          // Clear rewards for tracking but preserve the environment Z
          websocketService.send({
            type: "clear_active_rewards",
            preserve_z: true
          });
          
          rewardStore.cleanRewardsLocal();
        }

        // Send the rewards to the server with appropriate flag
        // Use websocketService.send which now handles queuing
        console.log(
          "Sending rewards to server with rewardsArray:",
          rewardsArray
        );
        
        // When processing rewards, check if they are from auto-capture
        const isAutoRewards = rewardsArray.some(r => r.auto_capture === true);
        
        // Enable batch mode when sending multiple rewards
        const isBatchMode = rewardsArray.length > 1;
        console.log(
          isBatchMode ? "Using batch mode for multiple rewards" : "Standard mode for single reward",
          isAutoRewards ? "(auto-capture)" : ""
        );
        
        websocketService.send({
          type: "request_reward",
          add_to_existing: addToExisting,
          batch_mode: isBatchMode, // Enable batch mode for multiple rewards
          auto_capture: isAutoRewards, // Flag for auto-capture rewards
          reward: {
            rewards: rewardsArray,
            weights: weights,
            combinationType: combinationType,
          },
        });

        // Update local store
        rewardsArray.forEach((reward, index) => {
          rewardStore.addReward(reward.name, {
            id: reward.id || uuidFn(),
            name: reward.name,
            ...reward,
          });

          if (weights[index] !== undefined) {
            rewardStore.updateWeight(index, weights[index]);
          }
        });
      }
    }
  } catch (error) {
    console.error("Error processing rewards", error);
  }
}

/**
 * Get last N lines of content for preview
 */
export function getLastLines(content, num = 3) {
  const lines = content.split("\n");
  return lines.slice(-num).join("\n");
}
