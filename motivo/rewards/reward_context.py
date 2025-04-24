import numpy as np
import torch
from humenv import rewards as humenv_rewards
from humenv.env import make_from_name
from metamotivo.wrappers.humenvbench import relabel
from rewards.task_rewards import (
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
    RightFootForwardDistanceReward,
    print_available_rewards
)
from rewards.behaviour_rewards import (
    StandingReward,
    UprightReward,
    MovementControlReward,
    SmallControlReward,
    PositionReward,
    BalanceReward,
    SymmetryReward,
    EnergyEfficiencyReward,
    NaturalMotionReward,
    GazeDirectionReward,
    GroundContactReward,
    StableStandingReward,
    NaturalWalkingReward
)
from rewards.position_rewards import PositionReward, PositionTarget
import inspect
import sys
from contextlib import nullcontext
import os
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
import torch.multiprocessing as mp
import atexit

# Create a global process executor
_global_process_executor = None

def get_process_executor(max_workers=None):
    """Get or create a global process executor"""
    global _global_process_executor
    if _global_process_executor is None:
        # Default to CPU count or user-specified worker count
        if max_workers is None:
            max_workers = min(os.cpu_count(), 8)  # Cap at 8 workers
        
        # Create the executor
        _global_process_executor = ProcessPoolExecutor(max_workers=max_workers)
        
        # Register cleanup function
        atexit.register(cleanup_process_executor)
        
        print(f"Created global process executor with {max_workers} workers")
    
    return _global_process_executor

def cleanup_process_executor():
    """Clean up the process executor on exit"""
    global _global_process_executor
    if _global_process_executor:
        print("Shutting down process executor...")
        _global_process_executor.shutdown(wait=False)
        _global_process_executor = None

def create_reward_function_for_process(rewards, combination_type):
    """Create a picklable reward function that can be passed to ProcessPoolExecutor"""
    def reward_fn(*args, **kwargs):
        return combine_rewards(rewards, combination_type, *args, **kwargs)
    return reward_fn

class RewardContextComputer:
    """Class to manage reward context computation with persistent resources"""
    
    def __init__(self, max_workers=None):
        """Initialize the reward context computer"""
        self.process_executor = get_process_executor(max_workers)
        self.current_rewards = None
        self.current_combination_type = None
    
    def additive_reward_fn(self, rewards, *args, **kwargs):
        """Additive reward combination"""
        total_reward = 0
        for reward_fn, weight in rewards:
            total_reward += weight * reward_fn(*args, **kwargs)
        return total_reward
    
    def multiplicative_reward_fn(self, rewards, *args, **kwargs):
        """Multiplicative reward combination"""
        total_reward = 1
        for reward_fn, weight in rewards:
            total_reward *= reward_fn(*args, **kwargs) ** weight
        return total_reward
    
    def min_reward_fn(self, rewards, *args, **kwargs):
        """Minimum reward combination"""
        rewards_list = []
        for reward_fn, weight in rewards:
            rewards_list.append(weight * reward_fn(*args, **kwargs))
        return min(rewards_list)
    
    def max_reward_fn(self, rewards, *args, **kwargs):
        """Maximum reward combination"""
        rewards_list = []
        for reward_fn, weight in rewards:
            rewards_list.append(weight * reward_fn(*args, **kwargs))
        return max(rewards_list)
    
    def geometric_mean_reward_fn(self, rewards, *args, **kwargs):
        """Geometric mean reward combination"""
        rewards_list = []
        for reward_fn, weight in rewards:
            rewards_list.append(max(1e-8, reward_fn(*args, **kwargs)) ** weight)
        return np.prod(rewards_list) ** (1.0 / len(rewards_list))

    def compute_reward(self, *args, **kwargs):
        """Class method to compute reward that can be pickled"""
        reward_combiners = {
            'additive': self.additive_reward_fn,
            'multiplicative': self.multiplicative_reward_fn,
            'min': self.min_reward_fn,
            'max': self.max_reward_fn,
            'geometric': self.geometric_mean_reward_fn
        }
        
        combined_reward_fn = reward_combiners.get(self.current_combination_type, self.additive_reward_fn)
        return combined_reward_fn(self.current_rewards, *args, **kwargs)

    def compute_reward_context(self, reward_config, env, model, buffer_data, use_gpu=True):
        """Compute reward context with optional GPU acceleration"""
        if not reward_config or 'rewards' not in reward_config or not reward_config['rewards']:
            print("\nNo rewards in configuration - using default context")
            return model.get_default_z() if hasattr(model, 'get_default_z') else model.prior.sample((1,))
            
        if use_gpu:
            return self.compute_reward_context_gpu(reward_config, env, model, buffer_data)
        else:
            return self.compute_reward_context_cpu(reward_config, env, model, buffer_data)
    
    def compute_reward_context_cpu(self, reward_config, env, model, buffer_data):
        """CPU implementation using persistent process executor"""
        combination_type = reward_config.get('combination_type', 'geometric')
        
        print("\n" + "="*50)
        print(f"USING REWARD COMBINATION METHOD: {combination_type.upper()} (CPU)")
        print("="*50 + "\n")
        
        batch_size = 10_000
        idx = np.random.randint(0, len(buffer_data['next_qpos']), batch_size)
        
        # Create the data batch with all keys from buffer_data
        batch = {}
        for key in buffer_data:
            if key in ['next_qpos', 'next_qvel', 'action', 'next_observation', 'B']:
                batch[key] = buffer_data[key][idx]
        
        # Create reward functions based on config
        rewards = []
        weights = reward_config.get('weights', [1.0])
        
        for reward_type, weight in zip(reward_config['rewards'], weights):
            rewards.append(create_reward_function(reward_type, weight))
        
        # Use the factory function instead of defining a local function
        reward_fn = create_reward_function_for_process(rewards, combination_type)
        
        print(f"Computing reward context with {combination_type} combination")
        computed_rewards = relabel(
            env,
            qpos=batch['next_qpos'],
            qvel=batch['next_qvel'],
            action=batch['action'],
            reward_fn=reward_fn,
            max_workers=40,
            process_executor=self.process_executor
        )
        
        print(f"Computed rewards: {computed_rewards}")
        
        # Prepare and return the inference result
        return self._prepare_inference_result(model, batch, computed_rewards)
    
    def compute_reward_context_gpu(self, reward_config, env, model, buffer_data):
        """GPU/MPS-accelerated implementation with optimized batching"""
        if not reward_config or 'rewards' not in reward_config or not reward_config['rewards']:
            print("\nNo rewards in configuration - using default context")
            return model.get_default_z() if hasattr(model, 'get_default_z') else model.prior.sample((1,))

        device, dtype = get_compute_device()
        if device.type == 'cpu':
            print("No GPU/MPS acceleration available, falling back to CPU")
            return self.compute_reward_context_cpu(reward_config, env, model, buffer_data)
        
        model = model.to(device)
        combination_type = reward_config.get('combination_type', 'geometric')
        
        print("\n" + "="*50)
        print(f"USING REWARD COMBINATION METHOD: {combination_type.upper()} ({device.type.upper()})")
        print("="*50 + "\n")
        
        batch_size = 750
        idx = np.random.randint(0, len(buffer_data['next_qpos']), batch_size)
        
        # Device-specific data transfer optimizations
        batch = self._prepare_batch_for_device(buffer_data, idx, device, dtype)
        
        # Create reward functions
        rewards = []
        weights = torch.tensor(reward_config.get('weights', [1.0]), device=device, dtype=dtype)
        
        for reward_type, weight in zip(reward_config['rewards'], weights):
            reward_tuple = create_reward_function(reward_type, weight)
            if reward_tuple is not None:
                rewards.append(reward_tuple)
        
        if not rewards:
            print("\nNo valid rewards could be created - using default context")
            return model.get_default_z() if hasattr(model, 'get_default_z') else model.prior.sample((1,))

        try:
            # Use the factory function instead of defining a local function
            reward_fn = create_reward_function_for_process(rewards, combination_type)
            
            # Try GPU-optimized computation first
            try:
                # Use custom parallel computation optimized for GPU
                rewards_list = []
                epsilon = torch.tensor(1e-8, device=device, dtype=dtype)
                
                for reward_fn, weight in rewards:
                    reward_result = parallel_reward_compute(
                        reward_fn, weight, batch, device, dtype, env,
                        process_executor=self.process_executor
                    )
                    if reward_result is not None:
                        rewards_list.append(torch.max(reward_result, epsilon))
                
                if not rewards_list:
                    raise ValueError("No valid rewards were computed")
                    
                # Combine rewards using geometric mean
                computed_rewards = torch.prod(torch.stack(rewards_list), dim=0) ** (1.0 / len(rewards_list))
            
            except Exception as e:
                print(f"GPU-optimized computation failed: {str(e)}, falling back to relabel")
                # Fall back to relabel - same approach as CPU
                qpos_np = batch['next_qpos'].cpu().numpy()
                qvel_np = batch['next_qvel'].cpu().numpy()
                action_np = batch['action'].cpu().numpy()
                
                computed_rewards = relabel(
                    env,
                    qpos=qpos_np,
                    qvel=qvel_np,
                    action=action_np,
                    reward_fn=reward_fn,  # Using the same picklable function
                    max_workers=8,
                    process_executor=self.process_executor
                )
                
                computed_rewards = torch.tensor(computed_rewards, device=device, dtype=dtype)
            
            # Prepare and return the inference result
            return self._prepare_inference_result(model, batch, computed_rewards)
            
        except Exception as e:
            print(f"Error in reward computation: {str(e)}")
            return model.get_default_z() if hasattr(model, 'get_default_z') else model.prior.sample((1,))
        finally:
            if device.type == 'cuda':
                torch.cuda.empty_cache()
    
    def _prepare_batch_for_device(self, buffer_data, idx, device, dtype):
        """Helper to prepare batch data for the specified device"""
        key_set = ['next_qpos', 'next_qvel', 'action', 'next_observation']
        # Add 'B' key if it exists
        if 'B' in buffer_data:
            key_set.append('B')
        
        if device.type == 'cuda':
            # For CUDA: Use pinned memory for faster transfers
            print(f"Using pinned memory optimization for CUDA transfer")
            pin_memory_batch = {}
            for key in key_set:
                if key in buffer_data:
                    # Create tensor on CPU with pinned memory
                    tensor_data = torch.tensor(buffer_data[key][idx], dtype=dtype).pin_memory()
                    # Store in dictionary
                    pin_memory_batch[key] = tensor_data
        
            # Transfer data to device with non_blocking=True for overlap
            batch = {
                k: v.to(device, non_blocking=True) for k, v in pin_memory_batch.items()
            }
            
            # Make sure the transfer is complete before proceeding
            torch.cuda.synchronize()
        else:
            # For CPU/MPS: Direct transfer is more appropriate
            batch = {
                k: torch.tensor(buffer_data[k][idx], device=device, dtype=dtype)
                for k in key_set if k in buffer_data
            }
        
        return batch

    def _prepare_inference_result(self, model, batch, computed_rewards):
        """Helper to prepare inference result from computed rewards"""
        device = next(model.parameters()).device
        
        # Ensure reward is properly shaped
        if isinstance(computed_rewards, torch.Tensor):
            reward_tensor = computed_rewards.reshape(-1, 1)
        else:
            reward_tensor = torch.tensor(computed_rewards, device=device).reshape(-1, 1)
        
        # Prepare the inference dictionary
        td = {"reward": reward_tensor}
        
        # Check if B exists in the batch data
        if "B" in batch:
            td["B_vect"] = batch["B"] if isinstance(batch["B"], torch.Tensor) else torch.tensor(batch["B"], device=device)
        else:
            td["next_obs"] = batch["next_observation"] if isinstance(batch["next_observation"], torch.Tensor) else torch.tensor(batch["next_observation"], device=device)
        
        # Get the inference function dynamically
        inference_fn_name = getattr(model, 'inference_function', 'reward_wr_inference')
        inference_fn = getattr(model, inference_fn_name, model.reward_wr_inference)
        
        # Call the inference function with the dictionary
        with torch.no_grad():
            z = inference_fn(**td).reshape(1, -1)
        
        #print(f"Computed z: {z}")
        return z

# Create global instance for backward compatibility
_reward_context_computer = None

def get_reward_context_computer(max_workers=None):
    """Get or create the global reward context computer"""
    global _reward_context_computer
    if _reward_context_computer is None:
        _reward_context_computer = RewardContextComputer(max_workers)
    return _reward_context_computer

# For backward compatibility - these functions use the global instance
def compute_reward_context(reward_config, env, model, buffer_data, use_gpu=True):
    """Compute reward context with optional GPU acceleration - using global instance"""
    computer = get_reward_context_computer()
    return computer.compute_reward_context(reward_config, env, model, buffer_data, use_gpu)

def compute_reward_context_cpu(reward_config, env, model, buffer_data):
    """CPU implementation using global instance"""
    computer = get_reward_context_computer()
    return computer.compute_reward_context_cpu(reward_config, env, model, buffer_data)

def compute_reward_context_gpu(reward_config, env, model, buffer_data):
    """GPU/MPS implementation using global instance"""
    computer = get_reward_context_computer()
    return computer.compute_reward_context_gpu(reward_config, env, model, buffer_data)

def create_reward_function(reward_type, weight):
    """Create a reward function based on config"""
    name = reward_type['name']
    
    # Try to create standard reward first
    all_rewards = inspect.getmembers(sys.modules["humenv.rewards"], inspect.isclass)
    for reward_class_name, reward_cls in all_rewards:
        if not inspect.isabstract(reward_cls):
            try:
                reward_obj = reward_cls.reward_from_name(name)
                if reward_obj is not None:
                    return (reward_obj, weight)
            except Exception as e:
                continue
    
    # Handle basic movements
    if name == 'jump':
        return (humenv_rewards.JumpReward(
            jump_height=reward_type.get('jump_height', 1.6),
            max_velocity=reward_type.get('max_velocity', 5.0)
        ), weight)
    elif name == 'rotation':
        return (humenv_rewards.RotationReward(
            axis=reward_type.get('axis', 'x'),
            target_ang_velocity=reward_type.get('target_ang_velocity', 5.0),
            stand_pelvis_height=reward_type.get('stand_pelvis_height', 0.95)
        ), weight)
    elif name == 'crawl':
        return (humenv_rewards.CrawlReward(
            spine_height=reward_type.get('spine_height', 0.3),
            move_angle=reward_type.get('move_angle', 0),
            move_speed=reward_type.get('move_speed', 1),
            direction=reward_type.get('direction', -1)
        ), weight)
    
    # Handle poses
    elif name == 'raisearms':
        return (humenv_rewards.ArmsReward(
            stand_height=reward_type.get('stand_height', 1.4),
            left_pose=reward_type.get('left_pose', 'h'),
            right_pose=reward_type.get('right_pose', 'h')
        ), weight)
    elif name == 'headstand':
        return (humenv_rewards.HeadstandReward(
            stand_pelvis_height=reward_type.get('stand_pelvis_height', 0.95)
        ), weight)
    elif name == 'liedown':
        return (humenv_rewards.LieDownReward(
            direction=reward_type.get('direction', 'up')
        ), weight)
    elif name == 'sit':
        return (humenv_rewards.SitOnGroundReward(
            pelvis_height_th=reward_type.get('pelvis_height_th', 0),
            constrained_knees=reward_type.get('constrained_knees', True),
            knees_not_on_ground=reward_type.get('knees_not_on_ground', False)
        ), weight)
    elif name == 'split':
        return (humenv_rewards.SplitReward(
            distance=reward_type.get('distance', 1.5)
        ), weight)
    
    # Handle custom reward types with consistent parameter naming
    if name == 'head-height':
        return (HeadHeightReward(target_height=reward_type.get('target_height', 1.4)), weight)
    elif name == 'pelvis-height':
        return (PelvisHeightReward(target_height=reward_type.get('target_height', 0.8)), weight)
    elif name == 'hand-height':
        return (HandHeightReward(target_height=reward_type.get('target_height', 1.8)), weight)
    elif name == 'hand-lateral':
        return (HandLateralDistanceReward(target_distance=reward_type.get('target_distance', 0.5)), weight)
    elif name == 'left-hand-height':
        return (LeftHandHeightReward(target_height=reward_type.get('target_height', 1.0)), weight)
    elif name == 'left-hand-lateral':
        return (LeftHandLateralDistanceReward(target_distance=reward_type.get('target_distance', 0.5)), weight)
    elif name == 'left-hand-forward':
        return (LeftHandForwardDistanceReward(target_distance=reward_type.get('target_distance', 0.5)), weight)
    elif name == 'right-hand-height':
        return (RightHandHeightReward(target_height=reward_type.get('target_height', 1.0)), weight)
    elif name == 'right-hand-lateral':
        return (RightHandLateralDistanceReward(target_distance=reward_type.get('target_distance', 0.5)), weight)
    elif name == 'right-hand-forward':
        return (RightHandForwardDistanceReward(target_distance=reward_type.get('target_distance', 0.5)), weight)
    elif name == 'left-foot-height':
        return (LeftFootHeightReward(target_height=reward_type.get('target_height', 0.1)), weight)
    elif name == 'left-foot-lateral':
        return (LeftFootLateralDistanceReward(
            target_distance=reward_type.get('target_distance', 0.2),
            debug=reward_type.get('debug', False)
        ), weight)
    elif name == 'left-foot-forward':
        return (LeftFootForwardDistanceReward(target_distance=reward_type.get('target_distance', 0.2)), weight)
    elif name == 'right-foot-height':
        return (RightFootHeightReward(target_height=reward_type.get('target_height', 0.1)), weight)
    elif name == 'right-foot-lateral':
        return (RightFootLateralDistanceReward(
            target_distance=reward_type.get('target_distance', 0.2),
            debug=reward_type.get('debug', False)
        ), weight)
    elif name == 'right-foot-forward':
        return (RightFootForwardDistanceReward(target_distance=reward_type.get('target_distance', 0.2)), weight)
    
    # Handle configurable rewards that need custom parameters
    if name == 'move-ego':
        return (humenv_rewards.LocomotionReward(
            move_speed=reward_type.get('move_speed', 2.0),
            stand_height=reward_type.get('stand_height', 1.4),
            move_angle=reward_type.get('move_angle', 0),
            egocentric_target=reward_type.get('egocentric_target', True),
            low_height=reward_type.get('low_height', 0.6),
            stay_low=reward_type.get('stay_low', False)
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
            loc_coeff=reward_type.get('loc_coeff', 1.0),
            visualize_target_angle=reward_type.get('visualize_target_angle', True)
        ), weight)
    
    # Handle custom reward types not in humenv.rewards
    elif name == 'stay-upright':
        return (StayUprightReward(), weight)
    
    # Handle behaviour rewards
    elif name == 'standing':
        return (StandingReward(target_height=reward_type.get('target_height', 0.95), tolerance=reward_type.get('tolerance', 0.05)), weight)
    elif name == 'upright':
        return (UprightReward(target_angle=reward_type.get('target_angle', 0.0), tolerance=reward_type.get('tolerance', 0.1)), weight)
    elif name == 'movement_control':
        return (MovementControlReward(max_velocity=reward_type.get('max_velocity', 1.0), max_acceleration=reward_type.get('max_acceleration', 5.0)), weight)
    elif name == 'small-control':
        return (SmallControlReward(margin=reward_type.get('margin', 1.0)), weight)
    elif name == 'balance':
        return (BalanceReward(max_com_velocity=reward_type.get('max_com_velocity', 0.1)), weight)
    elif name == 'symmetry':
        return (SymmetryReward(tolerance=reward_type.get('tolerance', 0.05)), weight)
    elif name == 'energy_efficiency':
        return (EnergyEfficiencyReward(max_control_cost=reward_type.get('max_control_cost', 1.0)), weight)
    elif name == 'natural_motion':
        return (NaturalMotionReward(max_jerk=reward_type.get('max_jerk', 10.0)), weight)
    elif name == 'gaze_direction':
        target_direction = reward_type.get('target_direction', [1, 0, 0])
        return (GazeDirectionReward(target_direction=target_direction, tolerance=reward_type.get('tolerance', 0.1)), weight)
    elif name == 'ground_contact':
        target_contacts = reward_type.get('target_contacts', ['L_Toe', 'R_Toe'])
        return (GroundContactReward(target_contacts=target_contacts, min_force=reward_type.get('min_force', 10.0)), weight)
    elif name == 'stable_standing':
        return (StableStandingReward(max_com_velocity=reward_type.get('max_com_velocity', 0.05), max_base_movement=reward_type.get('max_base_movement', 0.02)), weight)
    elif name == 'natural_walking':
        return (NaturalWalkingReward(target_speed=reward_type.get('target_speed', 1.2), max_step_variation=reward_type.get('max_step_variation', 0.1)), weight)
    
    # Handle position reward separately due to complex target structure
    if name == 'position':
        targets = {}
        for target in reward_type.get('targets', []):
            body_name = target['body']
            targets[body_name] = PositionTarget(
                x=target.get('x'),
                y=target.get('y'),
                z=target.get('z'),
                weight=target.get('weight', 1.0),
                sigmoid=target.get('sigmoid', 'linear'),
                margin=target.get('margin', 1.0)
            )
        
        return (PositionReward(
            targets=targets,
            upright_weight=reward_type.get('upright_weight', 0.3),
            control_weight=reward_type.get('control_weight', 0.2)
        ), weight)
    else:
        raise ValueError(f"Unknown reward type: {name}")

def compute_q_value(model, observation, z, action=None):
    """Compute Q-value using forward map and z projections"""
    device = next(model.parameters()).device  # Get the device from the model
    
    with torch.no_grad():
        # Move tensors to the same device as the model
        obs_tensor = torch.tensor(observation, device=device, dtype=torch.float32)
        if len(obs_tensor.shape) == 1:
            obs_tensor = obs_tensor.unsqueeze(0)
        
        # Ensure z is on the correct device and is a tensor
        if isinstance(z, torch.Tensor):
            z = z.to(device)
        else:
            z = torch.tensor(z, device=device, dtype=torch.float32)
            
        # If no action is provided, get the optimal action from the actor
        if action is None:
            action = model.act(obs_tensor, z, mean=True)
        else:
            # Handle various action input formats
            if isinstance(action, torch.Tensor):
                action = action.to(device)
            else:
                action = torch.tensor(action, device=device, dtype=torch.float32)
                
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

def get_compute_device():
    """Determine the best available compute device and appropriate dtype"""
    if torch.backends.mps.is_available():
        print("Using Apple Silicon MPS device")
        return torch.device('mps'), torch.float32
    elif torch.cuda.is_available():
        return torch.device('cuda'), torch.float32
    return torch.device('cpu'), torch.float64  # CPU can handle float64


def parallel_reward_compute(reward_fn, weight, batch_data, device, dtype, env, chunk_size=1000, scaler=None, process_executor=None):
    """Simplified reward computation with direct implementation"""
    batch_size = next(iter(batch_data.values())).shape[0]
    
    # Convert weight to correct dtype
    weight = torch.as_tensor(weight, device=device, dtype=dtype)
    
    # Convert data to numpy once
    qpos_np = batch_data['next_qpos'].cpu().numpy()
    qvel_np = batch_data['next_qvel'].cpu().numpy()
    action_np = batch_data['action'].cpu().numpy()
    
    # Vectorize reward computation if possible
    if hasattr(reward_fn, 'compute_vectorized'):
        # MPS doesn't support autocast, so we only use it for CUDA
        with (torch.cuda.amp.autocast() if device.type == 'cuda' else nullcontext()):
            rewards = reward_fn.compute_vectorized(
                env.unwrapped.model,
                qpos_np,
                qvel_np,
                action_np
            )
            rewards_tensor = torch.tensor(rewards, device=device, dtype=dtype)
            if scaler is not None and device.type == 'cuda':
                rewards_tensor = scaler.scale(rewards_tensor)
            return rewards_tensor * weight
    else:
        # Fallback to per-sample computation - use a single thread
        rewards_batch = torch.zeros(batch_size, device=device, dtype=dtype)
        for j in range(batch_size):
            with (torch.cuda.amp.autocast() if device.type == 'cuda' else nullcontext()):
                reward = reward_fn(
                    env.unwrapped.model,
                    qpos_np[j],
                    qvel_np[j],
                    action_np[j]
                )
                
                if scaler is not None and device.type == 'cuda':
                    reward = scaler.scale(torch.tensor(reward, device=device, dtype=dtype))
                else:
                    reward = torch.tensor(reward, device=device, dtype=dtype)
                
                rewards_batch[j] = reward * weight
        
        return rewards_batch

# Add this standalone function outside the class
def combine_rewards(rewards, combination_type, *args, **kwargs):
    """Standalone reward combination function that is picklable"""
    if combination_type == 'additive':
        total_reward = 0
        for reward_fn, weight in rewards:
            total_reward += weight * reward_fn(*args, **kwargs)
        return total_reward
    elif combination_type == 'multiplicative':
        total_reward = 1
        for reward_fn, weight in rewards:
            total_reward *= reward_fn(*args, **kwargs) ** weight
        return total_reward
    elif combination_type == 'min':
        rewards_list = []
        for reward_fn, weight in rewards:
            rewards_list.append(weight * reward_fn(*args, **kwargs))
        return min(rewards_list)
    elif combination_type == 'max':
        rewards_list = []
        for reward_fn, weight in rewards:
            rewards_list.append(weight * reward_fn(*args, **kwargs))
        return max(rewards_list)
    else:  # default to geometric
        rewards_list = []
        for reward_fn, weight in rewards:
            rewards_list.append(max(1e-8, reward_fn(*args, **kwargs)) ** weight)
        return np.prod(rewards_list) ** (1.0 / len(rewards_list)) 