import { RewardConfig } from '../types/rewards';

type Direction = 'up' | 'down';

export function getLieDownReward(direction: Direction = 'up'): RewardConfig {
  return {
    rewards: [
      { name: 'liedown', direction }
    ],
    weights: [1.0]
  };
} 