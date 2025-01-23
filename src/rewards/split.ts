import { RewardConfig } from '../types/rewards';

export function getSplitReward(distance: number = 1.5): RewardConfig {
  return {
    rewards: [
      { name: 'split', distance }
    ],
    weights: [1.0]
  };
} 