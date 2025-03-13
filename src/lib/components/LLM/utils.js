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
          result: directJson.result
        };
      }
    } catch (e) {
      // Not direct JSON, continue with other extraction methods
    }
    
    // Create structure
    let structured = {
      response: content, // Full response text
      explanation: "",   // Extracted explanation
      result: null       // Extracted rewards JSON
    };
    
    // Try to extract JSON from code blocks or content
    const jsonRegex = /```(?:json)?\s*(\{[\s\S]*?\})\s*```|`(\{[\s\S]*?\})`|(\{[\s\S]*?\})/g;
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
        const firstMatchIndex = content.indexOf('```');
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
    console.error('Error extracting structured response', error);
    return {
      response: content,
      explanation: content,
      result: null
    };
  }
}

/**
 * Process rewards from the LLM response
 */
export function processRewards(rewardData, rewardStore, websocketService, uuidFn) {
  try {
    // Handle both direct reward objects and objects containing a rewards array
    const rewardConfig = typeof rewardData === 'string' ? JSON.parse(rewardData) : rewardData;
    
    // Check if we have valid rewards data
    if (rewardConfig) {
      const rewardsArray = rewardConfig.rewards || (Array.isArray(rewardConfig) ? rewardConfig : null);
      
      if (rewardsArray && Array.isArray(rewardsArray)) {
        const ws = websocketService.getSocket();
        if (ws?.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({
            type: "clear_active_rewards"
          }));
        }
        
        rewardStore.cleanRewardsLocal();
        
        rewardsArray.forEach((reward, index) => {
          rewardStore.addReward(reward.name, {
            id: reward.id || uuidFn(),
            name: reward.name,
            ...reward
          });
          
          if (rewardConfig.weights?.[index] !== undefined) {
            rewardStore.updateWeight(index, rewardConfig.weights[index]);
          }
        });
      }
    }
  } catch (error) {
    console.error('Error processing rewards', error);
  }
}

/**
 * Get last N lines of content for preview
 */
export function getLastLines(content, num = 3) {
  const lines = content.split('\n');
  return lines.slice(-num).join('\n');
}