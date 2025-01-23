import { RewardConfig } from '../types/rewards';

export function getHeadstandReward(): RewardConfig {
  return {
    rewards: [
      { name: 'headstand', stand_pelvis_height: 0.95 }
    ],
    weights: [1.0]
  };
} 