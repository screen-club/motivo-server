# Rewards Components

This directory contains components and utilities for managing character behavior rewards.

## Components

### RewardPanel.svelte
The main panel for adding new rewards to the active set. Allows users to:
- Select a reward group
- Select a specific reward type from the group
- Configure parameters for the selected reward type
- Add the configured reward to the active set

### ActiveRewardsPanel.svelte
Displays and manages all currently active rewards. Features:
- Grid display of reward cards for all active rewards
- Configuration of reward combination type (geometric, additive, etc.)
- Option to save the current reward configuration as a favorite

### RewardCard.svelte
Individual card component for displaying and editing an active reward. Provides:
- Visual display of the reward name and parameters
- Controls for adjusting reward parameters
- Weight adjustment slider
- Update and remove actions

## Utilities

### RewardTypes.js
Central utility file for reward categorization and parameter handling:
- `REWARD_GROUPS`: Object mapping reward categories to their associated reward types
- `initializeParameters()`: Helper function to initialize parameters with default values
- `formatParameterLabel()`: Format parameter names for display
- `createRewardObject()`: Create a new reward object with default parameters
- `COMBINATION_TYPES`: Available combination types for aggregating multiple rewards

## State Management
Rewards state is primarily managed through:
- WebSocket communications with the server for active rewards
- RewardStore for local state management and synchronization

## Usage
The reward components work together to provide a complete rewards management system:
1. RewardPanel allows users to select and configure new rewards
2. Upon adding, rewards appear in the ActiveRewardsPanel
3. Users can then adjust weights and parameters or remove rewards as needed
4. The entire configuration can be saved for later use