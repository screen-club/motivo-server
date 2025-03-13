// GeminiClient.js - Handler for Gemini communication

import { io } from 'socket.io-client';
import { extractStructuredResponse, processRewards } from './utils.js';

/**
 * Creates a Gemini client for handling Gemini Vision model communication
 */
export function createGeminiClient(rewardStore, websocketService, addSystemMessage, uuidFn) {
  let flaskSocket = null;
  let isConnected = false;
  
  const connect = (apiUrl) => {
    try {
      flaskSocket = io(apiUrl, {
        transports: ['websocket'],
        reconnectionAttempts: 10,
        reconnectionDelay: 1000,
        timeout: 20000
      });
      
      flaskSocket.on('connect', () => {
        isConnected = true;
        flaskSocket.emit('gemini_connect');
      });
      
      flaskSocket.on('gemini_connection_status', (data) => {
        isConnected = data.connected;
      });
      
      flaskSocket.on('connect_error', () => {
        isConnected = false;
      });
      
      flaskSocket.on('disconnect', () => {
        isConnected = false;
      });
      
      return true;
    } catch (error) {
      console.error('Flask socket setup error', error);
      return false;
    }
  };
  
  const handleResponse = (data, geminiConversation) => {
    let updatedConversation = [...geminiConversation];
    let structuredResponse = null;
    
    if (data.content) {
      const lastMessage = updatedConversation[updatedConversation.length - 1];
      
      // Check if this is part of streaming response
      if (lastMessage && lastMessage.role === 'assistant' && !data.complete) {
        lastMessage.content = data.content;
        lastMessage.streaming = true;
      } else {
        // Final message or new message
        if (lastMessage && lastMessage.role === 'assistant' && data.complete) {
          lastMessage.content = data.content;
          lastMessage.streaming = false;
          
          // Extract structured data when complete
          structuredResponse = extractStructuredResponse(data.content);
          
          // Process rewards if available
          if (structuredResponse.result) {
            processRewards(structuredResponse.result, rewardStore, websocketService, uuidFn);
          }
        } else {
          updatedConversation.push({
            role: 'assistant',
            content: data.content,
            streaming: !data.complete
          });
          
          // Extract structured data if complete
          if (data.complete) {
            structuredResponse = extractStructuredResponse(data.content);
            
            // Process rewards if available
            if (structuredResponse.result) {
              processRewards(structuredResponse.result, rewardStore, websocketService, uuidFn);
            }
          }
        }
      }
    }
    
    return { 
      conversation: updatedConversation, 
      structuredResponse,
      isComplete: data.complete || false
    };
  };
  
  const checkConnection = () => {
    if (flaskSocket && flaskSocket.connected) {
      flaskSocket.emit('gemini_connect');
      return true;
    }
    return false;
  };
  
  const sendMessage = (message) => {
    if (flaskSocket && flaskSocket.connected) {
      flaskSocket.emit('gemini_message', { message });
      return true;
    } else {
      addSystemMessage('Error: Could not send message - Gemini service not connected');
      return false;
    }
  };
  
  const captureFrame = () => {
    if (flaskSocket && flaskSocket.connected) {
      flaskSocket.emit('gemini_capture');
      return true;
    }
    return false;
  };
  
  const disconnect = () => {
    if (flaskSocket) {
      flaskSocket.disconnect();
      flaskSocket = null;
      isConnected = false;
    }
  };
  
  const clearConversation = (clientId) => {
    const ws = websocketService.getSocket();
    if (ws?.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({
        type: "gemini_clear_conversation",
        client_id: clientId
      }));
      return true;
    }
    return false;
  };
  
  return {
    connect,
    handleResponse,
    checkConnection,
    sendMessage,
    captureFrame,
    disconnect,
    clearConversation,
    getIsConnected: () => isConnected
  };
}