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
      console.log(`Found ${matches.length} potential JSON matches in Gemini response`);
      
      // First, try to collect all rewards from all valid JSON blocks
      const allRewards = [];
      const allWeights = [];
      let combinationType = "geometric";
      
      for (const match of matches) {
        const jsonString = (match[1] || match[2] || match[3]).trim();
        try {
          const parsedJson = JSON.parse(jsonString);
          
          // Look for rewards array
          if (parsedJson.rewards && Array.isArray(parsedJson.rewards)) {
            // Collect all rewards
            allRewards.push(...parsedJson.rewards);
            
            // Collect weights if available
            if (parsedJson.weights && Array.isArray(parsedJson.weights)) {
              allWeights.push(...parsedJson.weights);
            } else {
              // Add placeholder weights of 1.0 for each reward
              allWeights.push(...Array(parsedJson.rewards.length).fill(1.0));
            }
            
            // Track combinationType (use the last one found)
            if (parsedJson.combinationType) {
              combinationType = parsedJson.combinationType;
            }
          } else if (parsedJson.result && parsedJson.result.rewards) {
            // Handle nested result structure
            allRewards.push(...parsedJson.result.rewards);
            
            if (parsedJson.result.weights) {
              allWeights.push(...parsedJson.result.weights);
            } else {
              allWeights.push(...Array(parsedJson.result.rewards.length).fill(1.0));
            }
            
            if (parsedJson.result.combinationType) {
              combinationType = parsedJson.result.combinationType;
            }
          }
          
          // Also check if we find a response field to use as explanation
          if (parsedJson.response && !structured.explanation) {
            structured.explanation = parsedJson.response;
          }
        } catch (e) {
          // Skip invalid JSON
          console.log("Invalid JSON in match:", e.message);
          continue;
        }
      }
      
      // If we found any rewards, consolidate them
      if (allRewards.length > 0) {
        console.log(`Consolidated ${allRewards.length} rewards from ${matches.length} JSON blocks`);
        structured.result = {
          rewards: allRewards,
          weights: allWeights,
          combinationType: combinationType
        };
      } else {
        // If no rewards were found, fall back to using the first valid JSON
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
    console.log("PROCESS REWARDS CALLED with data:", JSON.stringify(rewardData).substring(0, 500) + "...");
    console.log("addToExisting:", addToExisting);
    
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
        console.log("REWARD ARRAY LENGTH:", rewardsArray.length);
        console.log("REWARD NAMES:", rewardsArray.map(r => r.name).join(", "));
        
        // Only clear rewards if we're not adding to existing ones and it's not an auto-capture
        // AND if rewards haven't already been cleared in GeminiClient
        const isAutoCaptureReward = rewardsArray.some(r => r.auto_capture === true);
        const rewardsAlreadyCleared = rewardConfig.rewards_already_cleared === true;
        
        if (rewardsAlreadyCleared) {
          console.log("Rewards already cleared by parent component - skipping clearing phase");
        } else if (!addToExisting && !isAutoCaptureReward) {
          console.log("Clearing existing rewards before adding new ones");
          // Use websocketService.send which now handles queuing
          websocketService.send({
            type: "clear_active_rewards",
            preserve_z: false
          });

          rewardStore.cleanRewardsLocal();
        } else if (isAutoCaptureReward && !rewardsAlreadyCleared) {
          console.log("Auto-capture reward detected - preserving environment while clearing reward array");
          // Send the clear command only if it hasn't been sent already
          websocketService.send({
            type: "clear_active_rewards",
            preserve_z: true
          });
          
          rewardStore.cleanRewardsLocal();
        }

        // When processing rewards, check if they are from auto-capture
        const isAutoRewards = rewardsArray.some(r => r.auto_capture === true);
        
        // Enable batch mode when sending multiple rewards
        const isBatchMode = rewardsArray.length > 1;
        console.log(
          `SENDING ${rewardsArray.length} REWARDS AS A SINGLE BATCH: ${isBatchMode ? "batch mode" : "standard mode"}`
        );
        
        // CRITICAL: All rewards must be sent in a single message to the backend
        // NOT as multiple individual requests
        websocketService.send({
          type: "request_reward",
          add_to_existing: addToExisting,
          batch_mode: true, // Always use batch mode
          auto_capture: isAutoRewards,
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
      } else {
        console.log("No valid rewards array found", rewardConfig);
      }
    } else {
      console.log("No valid reward configuration");
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
