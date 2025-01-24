import numpy as np
import torch
from humenv import rewards as humenv_rewards
from humenv.env import make_from_name
from metamotivo.wrappers.humenvbench import relabel
from custom_rewards import (
    StayUprightReward,
    HeadHeightReward,
    PelvisHeightReward,
    HandHeightReward,
    HandLateralDistanceReward,
    LeftHandHeightReward,
    LeftHandLateralDistanceReward,
    LeftHandForwardDistanceReward,
    RightHandHeightReward,
    RightHandLateralDistanceReward,
    RightHandForwardDistanceReward,
    LeftFootHeightReward,
    LeftFootLateralDistanceReward,
    LeftFootForwardDistanceReward,
    RightFootHeightReward,
    RightFootLateralDistanceReward,
    RightFootForwardDistanceReward
)

def create_reward_function(reward_type, weight):

    print("create_reward_function")
    """Create a reward function based on config"""
    name = reward_type['name']
    
    if name == 'raisearms':
        left = reward_type.get('left', 'l')
        right = reward_type.get('right', 'l')
        valid_positions = {'l', 'm', 'h'}
        if left not in valid_positions or right not in valid_positions:
            raise ValueError(f"Invalid arm position. Must be one of: {valid_positions}")
        task_name = f"raisearms-{left}-{right}"
        return (make_from_name(task_name), weight)
    
    elif name.startswith('move-ego-'):
        return (make_from_name(name), weight)
    
    elif name == 'move-ego':
        stay_low = reward_type.get('stay_low', False)
        return (humenv_rewards.LocomotionReward(
            move_speed=reward_type.get('move_speed', 2.0),
            stand_height=reward_type.get('stand_height', 1.4),
            move_angle=reward_type.get('move_angle', 0),
            egocentric_target=reward_type.get('egocentric_target', True),
            low_height=reward_type.get('low_height', 0.6),
            stay_low=stay_low
        ), weight)
    
    elif name == 'move-and-raise-arms':
        return (humenv_rewards.MoveAndRaiseArmsReward(
            move_speed=reward_type.get('move_speed', 2.0),
            move_angle=reward_type.get('move_angle', 0),
            left_pose=reward_type.get('left_pose', 'h'),
            right_pose=reward_type.get('right_pose', 'h'),
            stand_height=reward_type.get('stand_height', 1.4),
            low_height=reward_type.get('low_height', 0.6),
            stay_low=reward_type.get('stay_low', False),
            egocentric_target=reward_type.get('egocentric_target', True),
            arm_coeff=reward_type.get('arm_coeff', 1.0),
            loc_coeff=reward_type.get('loc_coeff', 1.0)
        ), weight)
    
    elif name == 'jump':
        return (humenv_rewards.JumpReward(
            jump_height=reward_type.get('jump_height', 1.6),
            max_velocity=reward_type.get('max_velocity', 5.0)
        ), weight)
    
    elif name == 'zero':
        return (humenv_rewards.ZeroReward(), weight)
    
    elif name == 'rotation':
        return (humenv_rewards.RotationReward(
            axis=reward_type.get('axis', 'x'),
            target_ang_velocity=reward_type.get('target_ang_velocity', 5.0),
            stand_pelvis_height=reward_type.get('stand_pelvis_height', 0.8)
        ), weight)
    
    elif name == 'headstand':
        return (humenv_rewards.HeadstandReward(
            stand_pelvis_height=reward_type.get('stand_pelvis_height', 0.95)
        ), weight)
    
    elif name == 'crawl':
        direction = 1 if reward_type.get('direction', 'u') == 'u' else -1
        return (humenv_rewards.CrawlReward(
            spine_height=reward_type.get('spine_height', 0.3),
            move_speed=reward_type.get('move_speed', 1.0),
            direction=direction
        ), weight)
    
    elif name == 'liedown':
        return (humenv_rewards.LieDownReward(
            direction=reward_type.get('direction', 'up')
        ), weight)
    
    elif name == 'sit':
        return (humenv_rewards.SitOnGroundReward(
            pelvis_height_th=reward_type.get('pelvis_height_th', 0),
            constrained_knees=reward_type.get('constrained_knees', False)
        ), weight)
    
    elif name == 'split':
        return (humenv_rewards.SplitReward(
            distance=reward_type.get('distance', 1.5)
        ), weight)
    
    elif name == 'stay-upright':
        return (StayUprightReward(), weight)
    
    elif name == 'head-height':
        return (HeadHeightReward(
            target_height=reward_type.get('target_height', 1.4)
        ), weight)
    
    elif name == 'pelvis-height':
        return (PelvisHeightReward(
            target_height=reward_type.get('target_height', 0.8)
        ), weight)
    
    elif name == 'hand-height':
        return (HandHeightReward(
            target_height=reward_type.get('target_height', 1.8)
        ), weight)
    
    elif name == 'hand-lateral':
        return (HandLateralDistanceReward(
            target_distance=reward_type.get('target_distance', 0.5)
        ), weight)
    
    elif name == 'left-hand-height':
        return (LeftHandHeightReward(
            target_height=reward_type.get('target_height', 1.0)
        ), weight)
    
    elif name == 'left-hand-lateral':
        return (LeftHandLateralDistanceReward(
            target_distance=reward_type.get('target_distance', 0.5)
        ), weight)
    
    elif name == 'left-hand-forward':
        return (LeftHandForwardDistanceReward(
            target_distance=reward_type.get('target_distance', 0.5)
        ), weight)
    
    elif name == 'right-hand-height':
        return (RightHandHeightReward(
            target_height=reward_type.get('target_height', 1.0)
        ), weight)
    
    elif name == 'right-hand-lateral':
        return (RightHandLateralDistanceReward(
            target_distance=reward_type.get('target_distance', 0.5)
        ), weight)
    
    elif name == 'right-hand-forward':
        return (RightHandForwardDistanceReward(
            target_distance=reward_type.get('target_distance', 0.5)
        ), weight)
    
    elif name == 'left-foot-height':
        return (LeftFootHeightReward(
            target_height=reward_type.get('target_height', 0.1)
        ), weight)
    
    elif name == 'left-foot-lateral':
        return (LeftFootLateralDistanceReward(
            target_distance=reward_type.get('target_distance', 0.2)
        ), weight)
    
    elif name == 'left-foot-forward':
        return (LeftFootForwardDistanceReward(
            target_distance=reward_type.get('target_distance', 0.2)
        ), weight)
    
    elif name == 'right-foot-height':
        return (RightFootHeightReward(
            target_height=reward_type.get('target_height', 0.1)
        ), weight)
    
    elif name == 'right-foot-lateral':
        return (RightFootLateralDistanceReward(
            target_distance=reward_type.get('target_distance', 0.2)
        ), weight)
    
    elif name == 'right-foot-forward':
        return (RightFootForwardDistanceReward(
            target_distance=reward_type.get('target_distance', 0.2)
        ), weight)
    
    else:
        raise ValueError(f"Unknown reward type: {name}")

def compute_reward_context(reward_config, env, model, buffer_data):
    """Compute reward context"""
    combination_type = reward_config.get('combination_type', 'additive')
    
    print("\n" + "="*50)
    print(f"USING REWARD COMBINATION METHOD: {combination_type.upper()}")
    print("="*50 + "\n")
    
    batch_size = 10_000
    idx = np.random.randint(0, len(buffer_data['next_qpos']), batch_size)
    
    batch = {
        'next_qpos': buffer_data['next_qpos'][idx],
        'next_qvel': buffer_data['next_qvel'][idx],
        'action': buffer_data['action'][idx],
        'next_observation': buffer_data['next_observation'][idx]
    }
    
    # Create reward functions based on config
    rewards = []
    weights = reward_config.get('weights', [1.0])
    
    for reward_type, weight in zip(reward_config['rewards'], weights):
        rewards.append(create_reward_function(reward_type, weight))
    
    def additive_reward_fn(*args, **kwargs):
        total_reward = 0
        for reward_fn, weight in rewards:
            total_reward += weight * reward_fn(*args, **kwargs)
        return total_reward
    
    def multiplicative_reward_fn(*args, **kwargs):
        total_reward = 1
        for reward_fn, weight in rewards:
            total_reward *= reward_fn(*args, **kwargs) ** weight
        return total_reward
    
    def min_reward_fn(*args, **kwargs):
        rewards_list = []
        for reward_fn, weight in rewards:
            rewards_list.append(weight * reward_fn(*args, **kwargs))
        return min(rewards_list)
    
    def max_reward_fn(*args, **kwargs):
        rewards_list = []
        for reward_fn, weight in rewards:
            rewards_list.append(weight * reward_fn(*args, **kwargs))
        return max(rewards_list)
    
    def geometric_mean_reward_fn(*args, **kwargs):
        rewards_list = []
        for reward_fn, weight in rewards:
            rewards_list.append(max(1e-8, reward_fn(*args, **kwargs)) ** weight)
        return np.prod(rewards_list) ** (1.0 / len(rewards_list))

    reward_combiners = {
        'additive': additive_reward_fn,
        'multiplicative': multiplicative_reward_fn,
        'min': min_reward_fn,
        'max': max_reward_fn,
        'geometric': geometric_mean_reward_fn
    }
    
    combined_reward_fn = reward_combiners.get(combination_type, additive_reward_fn)
    
    computed_rewards = relabel(
        env,
        qpos=batch['next_qpos'],
        qvel=batch['next_qvel'],
        action=batch['action'],
        reward_fn=combined_reward_fn,
        max_workers=8
    )
    
    z = model.reward_wr_inference(
        next_obs=torch.tensor(batch['next_observation'], device=model.cfg.device, dtype=torch.float32),
        reward=torch.tensor(computed_rewards, device=model.cfg.device, dtype=torch.float32)
    )
    
    return z

def compute_q_value(model, observation, z, action=None):
    """Compute Q-value using forward map and z projections"""
    with torch.no_grad():
        obs_tensor = torch.tensor(observation, device=model.cfg.device, dtype=torch.float32)
        if len(obs_tensor.shape) == 1:
            obs_tensor = obs_tensor.unsqueeze(0)
            
        # If no action is provided, get the optimal action from the actor
        if action is None:
            action = model.act(obs_tensor, z, mean=True)
        else:
            action = torch.tensor(action, device=model.cfg.device, dtype=torch.float32)
            if len(action.shape) == 1:
                action = action.unsqueeze(0)
        
        # Compute forward map
        F = model.forward_map(
            obs=obs_tensor, 
            z=z.repeat(obs_tensor.shape[0], 1), 
            action=action
        )
        
        # Compute z_reward using backward map
        z_reward = torch.sum(
            model.backward_map(obs=obs_tensor) * z,
            dim=0
        )
        z_reward = model.project_z(z_reward)
        
        # Compute Q-value using matrix multiplication
        Q = F @ z_reward.ravel()
        return Q.mean(axis=0).cpu().numpy().item()  # Convert to Python scalar 