import { RewardConfig } from '../types/rewards';

interface CrawlOptions {
  direction?: 1 | -1;  // 1 for up, -1 for down
}

export function getCrawlReward(options: CrawlOptions = {}): RewardConfig {
  const { direction = 1 } = options;
  
  return {
    rewards: [
      {
        name: 'crawl',
        spine_height: 0.4,
        move_speed: 2.0,
        direction
      }
    ],
    weights: [1.0]
  };
} 