// ClaudeClient.js - Handler for Claude communication

import { processRewards } from './utils.js';

/**
 * Creates a Claude client for handling Claude model communication
 */
export function createClaudeClient(chatStore, rewardStore, websocketService, uuidFn) {
  
  const sendMessage = async (apiUrl, prompt, sessionId) => {
    try {
      const res = await fetch(`${apiUrl}/generate-reward`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          prompt,
          sessionId
        })
      });

      const data = await res.json();
      
      if (data.error) {
        throw new Error(data.error);
      }

      // Update chatStore for maintaining state
      chatStore.update(store => ({
        ...store,
        sessionId: data.sessionId,
        response: data.reward_config,
        conversation: data.conversation
      }));

      try {
        const rewardConfig = JSON.parse(data.reward_config);
        
        if (rewardConfig.rewards && Array.isArray(rewardConfig.rewards)) {
          processRewards(rewardConfig, rewardStore, websocketService, uuidFn);
        }
      } catch (e) {
        console.error('Error processing reward configuration', e);
      }

      return {
        conversation: data.conversation,
        success: true
      };
    } catch (error) {
      console.error('Error in Claude API call', error);
      chatStore.update(store => ({
        ...store,
        response: `Error: ${error.message}`
      }));
      
      return {
        error: error.message,
        success: false
      };
    }
  };
  
  const clearConversation = async (apiUrl, sessionId) => {
    try {
      const res = await fetch(`${apiUrl}/clear-chat`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ sessionId })
      });

      if (!res.ok) throw new Error('Failed to clear chat');
      
      // Update the chatStore
      chatStore.update(store => ({
        ...store,
        conversation: [],
        response: ''
      }));
      
      return true;
    } catch (error) {
      console.error('Error clearing Claude chat', error);
      return false;
    }
  };
  
  return {
    sendMessage,
    clearConversation
  };
}