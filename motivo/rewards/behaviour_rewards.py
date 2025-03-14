"""
Core reward components for humanoid control.
These can be used individually or combined to create complex behaviors.
"""

import numpy as np
from humenv import rewards as humenv_rewards
from dm_control.utils import rewards
import mujoco
from typing import Optional
import dataclasses

# Utility functions
def get_xpos(model, data, name, fallback=None):
    """Get position of a named body with safe fallback option."""
    try:
        return data.xpos[model.body(name).id]
    except Exception:
        if fallback:
            try:
                return data.xpos[model.body(fallback).id]
            except Exception:
                return None
        return None

def get_xmat(model, data, name, fallback=None):
    """Get rotation matrix of a named body with safe fallback option."""
    try:
        return data.xmat[model.body(name).id].reshape(3, 3)
    except Exception:
        if fallback:
            try:
                return data.xmat[model.body(fallback).id].reshape(3, 3)
            except Exception:
                return None
        return None

def get_chest_upright(model, data):
    """Get upright value of the chest."""
    try:
        return data.xmat[model.body('Torso').id][2, 2]
    except Exception:
        try:
            # Fallback to Chest or Spine if Torso isn't available
            return data.xmat[model.body('Chest').id][2, 2]
        except Exception:
            try:
                return data.xmat[model.body('Spine').id][2, 2]
            except Exception:
                return 0.0  # Default value if all attempts fail

def get_center_of_mass(model, data):
    """Calculate center of mass of the humanoid."""
    total_mass = 0
    weighted_pos = np.zeros(3)
    
    for i in range(model.nbody):
        mass = model.body_mass[i]
        pos = data.xpos[i]
        weighted_pos += mass * pos
        total_mass += mass
    
    return weighted_pos / total_mass

def get_center_of_mass_linvel(model, data):
    """Calculate linear velocity of the center of mass."""
    total_mass = 0
    weighted_vel = np.zeros(3)
    
    for i in range(model.nbody):
        mass = model.body_mass[i]
        vel = data.cvel[i][:3]  # Linear velocity component
        weighted_vel += mass * vel
        total_mass += mass
    
    return weighted_vel / total_mass

@dataclasses.dataclass
class StandingReward(humenv_rewards.RewardFunction):
    """Rewards maintaining a target standing height."""
    target_height: float = 1.4
    margin: float = 0.2

    @classmethod
    def reward_from_name(cls, name):
        if name == 'standing':
            return cls()
        return None

    def compute(self, model: mujoco.MjModel, data: mujoco.MjData) -> float:
        head_height = get_xpos(model, data, name="Head")[-1]
        return rewards.tolerance(
            head_height,
            bounds=(self.target_height, float("inf")),
            margin=self.margin,
            value_at_margin=0.01,
            sigmoid="linear"
        )

@dataclasses.dataclass
class UprightReward(humenv_rewards.RewardFunction):
    """Rewards maintaining an upright posture."""
    min_upright: float = 0.9
    margin: float = 1.9

    @classmethod
    def reward_from_name(cls, name):
        if name == 'upright':
            return cls()
        return None

    def compute(self, model: mujoco.MjModel, data: mujoco.MjData) -> float:
        chest_upright = get_chest_upright(model, data)
        return rewards.tolerance(
            chest_upright,
            bounds=(self.min_upright, float("inf")),
            sigmoid="linear",
            margin=self.margin,
            value_at_margin=0
        )

@dataclasses.dataclass
class MovementControlReward(humenv_rewards.RewardFunction):
    """Penalizes excessive movement."""
    margin: float = 0.5

    @classmethod
    def reward_from_name(cls, name):
        if name == 'movement-control':
            return cls()
        return None

    def compute(self, model: mujoco.MjModel, data: mujoco.MjData) -> float:
        velocity = get_center_of_mass_linvel(model, data)
        return rewards.tolerance(
            velocity, 
            margin=self.margin
        ).mean()

@dataclasses.dataclass
class SmallControlReward(humenv_rewards.RewardFunction):
    """Penalizes large control inputs."""
    margin: float = 1.0
    weight: float = 0.8  # (4/5)

    @classmethod
    def reward_from_name(cls, name):
        if name == 'small-control':
            return cls()
        return None

    def compute(self, model: mujoco.MjModel, data: mujoco.MjData) -> float:
        control = rewards.tolerance(
            data.ctrl, 
            margin=self.margin, 
            value_at_margin=0, 
            sigmoid="quadratic"
        ).mean()
        return (self.weight * control) + (1 - self.weight)

@dataclasses.dataclass
class PositionTarget:
    """Target position specification for a body part."""
    # Target position components (None means don't care about this axis)
    x: Optional[float] = None
    y: Optional[float] = None
    z: Optional[float] = None
    
    # Per-axis margins (defaults if not specified)
    x_margin: float = 0.1
    y_margin: float = 0.1
    z_margin: float = 0.1
    
    # Relative position to the reference body (None for absolute position)
    relative_to: Optional[str] = None
    
    # Alternative body parts to try if the main one isn't found
    alternatives: list = dataclasses.field(default_factory=list)
    
    # Weighting for this target when multiple targets are used
    weight: float = 1.0

@dataclasses.dataclass
class PositionReward(humenv_rewards.RewardFunction):
    """Rewards achieving target positions for specific body parts.
    
    Much more robust with support for:
    - Multiple body targets with independent weights
    - Relative positioning to reference bodies
    - Axis-specific targets (ignore axes you don't care about)
    - Alternative body names for different models
    - Detailed debugging output
    - Fallback behavior when bodies aren't found
    """
    # A dictionary mapping body names to their targets
    targets: dict = dataclasses.field(default_factory=dict)
    # How much to weight orientation vs. position
    orientation_weight: float = 0.0
    # Target orientation (quaternion format)
    target_orientation: Optional[np.ndarray] = None
    # Whether to use global or local coordinates
    use_global_coords: bool = True
    # Debug mode
    debug: bool = False
    # Whether to fail silently if targets are not found
    allow_missing_targets: bool = True
    # How much to weight postural terms (upright, control)
    upright_weight: float = 0.0
    control_weight: float = 0.0
    
    @classmethod
    def reward_from_name(cls, name):
        if name == 'position':
            return cls()
        return None

    def compute(self, model: mujoco.MjModel, data: mujoco.MjData) -> float:
        if not self.targets:
            if self.debug:
                print("Warning: No position targets specified")
            return 0.0
            
        total_reward = 0.0
        total_weight = 0.0
        
        # Process each target
        for body_name, target in self.targets.items():
            reward_value = self._compute_for_body(model, data, body_name, target)
            if reward_value is not None:
                total_reward += target.weight * reward_value
                total_weight += target.weight
            elif not self.allow_missing_targets:
                # If target is required and missing, return 0
                if self.debug:
                    print(f"Required target {body_name} not found, failing reward")
                return 0.0
        
        # Add upright component if specified
        if self.upright_weight > 0:
            upright_reward = UprightReward().compute(model, data)
            total_reward += self.upright_weight * upright_reward
            total_weight += self.upright_weight
            
            if self.debug:
                print(f"Upright component: {upright_reward:.3f}")
        
        # Add control component if specified
        if self.control_weight > 0:
            control_reward = SmallControlReward().compute(model, data)
            total_reward += self.control_weight * control_reward
            total_weight += self.control_weight
            
            if self.debug:
                print(f"Control component: {control_reward:.3f}")
        
        # Normalize by total weight
        if total_weight > 0:
            final_reward = total_reward / total_weight
        else:
            if self.debug:
                print("Warning: No valid targets found for position reward")
            final_reward = 0.0
            
        if self.debug:
            print(f"Position reward total: {final_reward:.3f}")
            
        return final_reward
    
    def _compute_for_body(self, model, data, body_name, target):
        """Compute reward for a single body target."""
        # Try to find the body position
        body_pos = self._get_body_position(model, data, body_name, target.alternatives)
        if body_pos is None:
            if self.debug:
                print(f"Warning: Could not find position for {body_name} or its alternatives")
            return None
            
        # Get reference position if relative positioning is used
        ref_pos = np.zeros(3)
        if target.relative_to is not None:
            ref_pos = self._get_body_position(model, data, target.relative_to)
            if ref_pos is None:
                if self.debug:
                    print(f"Warning: Could not find reference body {target.relative_to}")
                return None
        
        # Calculate position error for each axis that has a target
        axis_rewards = []
        rel_pos = body_pos - ref_pos
        
        if target.x is not None:
            x_error = abs(rel_pos[0] - target.x)
            x_reward = rewards.tolerance(
                x_error, 
                bounds=(0, 0.05),
                margin=target.x_margin,
                value_at_margin=0.01,
                sigmoid="linear"
            )
            axis_rewards.append(x_reward)
            if self.debug:
                print(f"Body {body_name} X: target={target.x:.3f}, actual={rel_pos[0]:.3f}, error={x_error:.3f}, reward={x_reward:.3f}")
        
        if target.y is not None:
            y_error = abs(rel_pos[1] - target.y)
            y_reward = rewards.tolerance(
                y_error, 
                bounds=(0, 0.05),
                margin=target.y_margin,
                value_at_margin=0.01,
                sigmoid="linear"
            )
            axis_rewards.append(y_reward)
            if self.debug:
                print(f"Body {body_name} Y: target={target.y:.3f}, actual={rel_pos[1]:.3f}, error={y_error:.3f}, reward={y_reward:.3f}")
                
        if target.z is not None:
            z_error = abs(rel_pos[2] - target.z)
            z_reward = rewards.tolerance(
                z_error, 
                bounds=(0, 0.05),
                margin=target.z_margin,
                value_at_margin=0.01,
                sigmoid="linear"
            )
            axis_rewards.append(z_reward)
            if self.debug:
                print(f"Body {body_name} Z: target={target.z:.3f}, actual={rel_pos[2]:.3f}, error={z_error:.3f}, reward={z_reward:.3f}")
        
        # If no axis was specified, use overall distance
        if not axis_rewards:
            # All axes - use Euclidean distance
            target_pos = np.array([
                target.x if target.x is not None else rel_pos[0],
                target.y if target.y is not None else rel_pos[1],
                target.z if target.z is not None else rel_pos[2]
            ])
            distance = np.linalg.norm(rel_pos - target_pos)
            body_reward = rewards.tolerance(
                distance,
                bounds=(0, 0.05),
                margin=max(target.x_margin, target.y_margin, target.z_margin),
                value_at_margin=0.01,
                sigmoid="linear"
            )
            if self.debug:
                print(f"Body {body_name} distance: {distance:.3f}, reward={body_reward:.3f}")
        else:
            # Return average of axis rewards
            body_reward = sum(axis_rewards) / len(axis_rewards)
        
        return body_reward
    
    def _get_body_position(self, model, data, body_name, alternatives=None):
        """Safely get a body position with fallbacks for different joint names."""
        # Try the primary body name
        try:
            body_pos = get_xpos(model, data, body_name)
            if body_pos is not None:
                return body_pos
        except:
            pass
            
        # Try alternatives if provided
        if alternatives:
            for alt_name in alternatives:
                try:
                    body_pos = get_xpos(model, data, alt_name)
                    if body_pos is not None:
                        if self.debug:
                            print(f"Using alternative {alt_name} for {body_name}")
                        return body_pos
                except:
                    continue
                    
        # Special case handling for common body parts
        if body_name.lower().endswith(('hand', 'wrist')):
            # Try hand/wrist pairs
            if 'left' in body_name.lower() or 'l_' in body_name.lower():
                try_parts = ['L_Hand', 'L_Wrist', 'LeftHand', 'left_hand', 'left_wrist']
            else:
                try_parts = ['R_Hand', 'R_Wrist', 'RightHand', 'right_hand', 'right_wrist']
                
            for part in try_parts:
                try:
                    body_pos = get_xpos(model, data, part)
                    if body_pos is not None:
                        if self.debug:
                            print(f"Using {part} as fallback for {body_name}")
                        return body_pos
                except:
                    continue
                    
        elif body_name.lower().endswith(('foot', 'toe', 'ankle')):
            # Try foot/toe/ankle groups
            if 'left' in body_name.lower() or 'l_' in body_name.lower():
                try_parts = ['L_Toe', 'L_Foot', 'L_Ankle', 'LeftFoot', 'left_foot']
            else:
                try_parts = ['R_Toe', 'R_Foot', 'R_Ankle', 'RightFoot', 'right_foot']
                
            for part in try_parts:
                try:
                    body_pos = get_xpos(model, data, part)
                    if body_pos is not None:
                        if self.debug:
                            print(f"Using {part} as fallback for {body_name}")
                        return body_pos
                except:
                    continue
                    
        # Could not find the body
        return None

@dataclasses.dataclass
class BalanceReward(humenv_rewards.RewardFunction):
    """Rewards maintaining balance over the support polygon."""
    margin: float = 0.2
    debug: bool = False

    @classmethod
    def reward_from_name(cls, name):
        if name == 'balance':
            return cls()
        return None

    def compute(self, model: mujoco.MjModel, data: mujoco.MjData) -> float:
        com = get_center_of_mass(model, data)
        
        # Get left foot position - try multiple joints
        l_toe = get_xpos(model, data, "L_Toe")
        l_ankle = get_xpos(model, data, "L_Ankle")
        left_foot_pos = None
        
        if l_toe is not None and l_ankle is not None:
            left_foot_pos = (l_toe + l_ankle) / 2
        elif l_toe is not None:
            left_foot_pos = l_toe
        elif l_ankle is not None:
            left_foot_pos = l_ankle
        else:
            # Try other foot joints if available
            left_foot_pos = get_xpos(model, data, "L_Foot", "L_LeftFoot")
        
        # Get right foot position - try multiple joints
        r_toe = get_xpos(model, data, "R_Toe")
        r_ankle = get_xpos(model, data, "R_Ankle")
        right_foot_pos = None
        
        if r_toe is not None and r_ankle is not None:
            right_foot_pos = (r_toe + r_ankle) / 2
        elif r_toe is not None:
            right_foot_pos = r_toe
        elif r_ankle is not None:
            right_foot_pos = r_ankle
        else:
            # Try other foot joints if available
            right_foot_pos = get_xpos(model, data, "R_Foot", "R_RightFoot")
        
        # If either foot position is missing, return minimal reward
        if left_foot_pos is None or right_foot_pos is None:
            if self.debug:
                print("Warning: Could not find foot positions for balance calculation")
            return 0.0
        
        # Calculate the center of the support polygon
        feet_center = (left_foot_pos + right_foot_pos) / 2
        horizontal_distance = np.linalg.norm(com[:2] - feet_center[:2])
        
        if self.debug:
            print(f"Balance: COM={com[:2]}, Feet center={feet_center[:2]}, Distance={horizontal_distance:.3f}")
        
        return rewards.tolerance(
            horizontal_distance,
            bounds=(0, 0.1),
            margin=self.margin,
            sigmoid="linear"
        )

@dataclasses.dataclass
class SymmetryReward(humenv_rewards.RewardFunction):
    """Rewards symmetric postures."""
    weight_hands: float = 0.5
    weight_feet: float = 0.5
    margin: float = 0.2
    debug: bool = False

    @classmethod
    def reward_from_name(cls, name):
        if name == 'symmetry':
            return cls()
        return None

    def compute(self, model: mujoco.MjModel, data: mujoco.MjData) -> float:
        # Get left and right hand positions - try multiple joints
        l_hand_pos = None
        l_hand = get_xpos(model, data, "L_Hand")
        l_wrist = get_xpos(model, data, "L_Wrist")
        
        if l_hand is not None and l_wrist is not None:
            l_hand_pos = (l_hand + l_wrist) / 2
        elif l_hand is not None:
            l_hand_pos = l_hand
        elif l_wrist is not None:
            l_hand_pos = l_wrist
        
        # Get right hand position
        r_hand_pos = None
        r_hand = get_xpos(model, data, "R_Hand")
        r_wrist = get_xpos(model, data, "R_Wrist")
        
        if r_hand is not None and r_wrist is not None:
            r_hand_pos = (r_hand + r_wrist) / 2
        elif r_hand is not None:
            r_hand_pos = r_hand
        elif r_wrist is not None:
            r_hand_pos = r_wrist
        
        # Get left foot position
        l_foot_pos = None
        l_toe = get_xpos(model, data, "L_Toe")
        l_ankle = get_xpos(model, data, "L_Ankle")
        
        if l_toe is not None and l_ankle is not None:
            l_foot_pos = (l_toe + l_ankle) / 2
        elif l_toe is not None:
            l_foot_pos = l_toe
        elif l_ankle is not None:
            l_foot_pos = l_ankle
        else:
            l_foot_pos = get_xpos(model, data, "L_Foot", "L_LeftFoot")
        
        # Get right foot position
        r_foot_pos = None
        r_toe = get_xpos(model, data, "R_Toe")
        r_ankle = get_xpos(model, data, "R_Ankle")
        
        if r_toe is not None and r_ankle is not None:
            r_foot_pos = (r_toe + r_ankle) / 2
        elif r_toe is not None:
            r_foot_pos = r_toe
        elif r_ankle is not None:
            r_foot_pos = r_ankle
        else:
            r_foot_pos = get_xpos(model, data, "R_Foot", "R_RightFoot")
        
        # Calculate symmetry for hands and feet if data is available
        hand_symmetry = 0.0
        if l_hand_pos is not None and r_hand_pos is not None:
            hand_symmetry = rewards.tolerance(
                np.abs(l_hand_pos[0] + r_hand_pos[0]),  # Should be close to 0 for perfect symmetry
                bounds=(0, 0.1),
                margin=self.margin,
                sigmoid="linear"
            )
            if self.debug:
                print(f"Hand symmetry: left={l_hand_pos[0]:.3f}, right={r_hand_pos[0]:.3f}, metric={np.abs(l_hand_pos[0] + r_hand_pos[0]):.3f}")
        
        foot_symmetry = 0.0
        if l_foot_pos is not None and r_foot_pos is not None:
            foot_symmetry = rewards.tolerance(
                np.abs(l_foot_pos[0] + r_foot_pos[0]),  # Should be close to 0 for perfect symmetry
                bounds=(0, 0.1),
                margin=self.margin,
                sigmoid="linear"
            )
            if self.debug:
                print(f"Foot symmetry: left={l_foot_pos[0]:.3f}, right={r_foot_pos[0]:.3f}, metric={np.abs(l_foot_pos[0] + r_foot_pos[0]):.3f}")
        
        # If no valid data for either hand or foot, adjust weights accordingly
        total_weight = 0
        total_reward = 0
        
        if l_hand_pos is not None and r_hand_pos is not None:
            total_reward += self.weight_hands * hand_symmetry
            total_weight += self.weight_hands
        
        if l_foot_pos is not None and r_foot_pos is not None:
            total_reward += self.weight_feet * foot_symmetry
            total_weight += self.weight_feet
        
        # Return normalized reward or default value if no data available
        if total_weight > 0:
            return total_reward / total_weight
        else:
            if self.debug:
                print("Warning: No valid joint positions for symmetry calculation")
            return 0.0

@dataclasses.dataclass
class EnergyEfficiencyReward(humenv_rewards.RewardFunction):
    """Rewards energy-efficient movements."""
    vel_margin: float = 1.0
    ctrl_margin: float = 0.5

    @classmethod
    def reward_from_name(cls, name):
        if name == 'energy-efficiency':
            return cls()
        return None

    def compute(self, model: mujoco.MjModel, data: mujoco.MjData) -> float:
        joint_vel_cost = rewards.tolerance(
            data.qvel,
            margin=self.vel_margin,
            value_at_margin=0,
            sigmoid="quadratic"
        ).mean()
        
        control_cost = rewards.tolerance(
            data.ctrl,
            margin=self.ctrl_margin,
            value_at_margin=0,
            sigmoid="quadratic"
        ).mean()
        
        return (joint_vel_cost + control_cost) / 2

@dataclasses.dataclass
class NaturalMotionReward(humenv_rewards.RewardFunction):
    """Rewards smooth, coordinated movements."""
    smoothness_weight: float = 0.5
    coordination_weight: float = 0.5

    @classmethod
    def reward_from_name(cls, name):
        if name == 'natural-motion':
            return cls()
        return None

    def compute(self, model: mujoco.MjModel, data: mujoco.MjData) -> float:
        # Compute motion smoothness based on velocity
        velocity_changes = np.diff(data.qvel)
        smoothness = 1.0 / (1.0 + np.mean(np.square(velocity_changes)))
        
        # Compute motion coordination based on joint velocities
        joint_correlations = np.corrcoef(data.qvel)
        coordination = np.mean(np.abs(joint_correlations))
        
        return (
            self.smoothness_weight * smoothness + 
            self.coordination_weight * coordination
        )

@dataclasses.dataclass
class GazeDirectionReward(humenv_rewards.RewardFunction):
    """Rewards looking at a specific target."""
    target_point: np.ndarray = dataclasses.field(default_factory=lambda: np.array([1.0, 0.0, 1.7]))
    angle_margin: float = 0.5

    @classmethod
    def reward_from_name(cls, name):
        if name == 'gaze-direction':
            return cls()
        return None

    def compute(self, model: mujoco.MjModel, data: mujoco.MjData) -> float:
        head_pos = get_xpos(model, data, "Head")
        head_rot = get_xmat(model, data, "Head")
        forward_vec = head_rot[:3, 0]
        
        target_dir = self.target_point - head_pos
        target_dir = target_dir / np.linalg.norm(target_dir)
        
        angle = np.arccos(np.clip(np.dot(forward_vec, target_dir), -1.0, 1.0))
        return rewards.tolerance(
            angle,
            bounds=(0, 0.1),
            margin=self.angle_margin,
            sigmoid="linear"
        )

@dataclasses.dataclass
class GroundContactReward(humenv_rewards.RewardFunction):
    """Rewards specific ground contact patterns."""
    desired_contacts: list = dataclasses.field(default_factory=lambda: ["L_Toe", "L_Foot", "R_Toe", "R_Foot"])
    contact_alternatives: dict = dataclasses.field(default_factory=lambda: {
        "L_Toe": ["L_Foot", "L_LeftFoot", "L_Ankle"],
        "R_Toe": ["R_Foot", "R_RightFoot", "R_Ankle"],
        "L_Foot": ["L_Toe", "L_LeftFoot", "L_Ankle"],
        "R_Foot": ["R_Toe", "R_RightFoot", "R_Ankle"]
    })
    debug: bool = False

    @classmethod
    def reward_from_name(cls, name):
        if name == 'ground-contact':
            return cls()
        return None

    def compute(self, model: mujoco.MjModel, data: mujoco.MjData) -> float:
        # Track which desired contact points have been detected
        contact_detected = {contact: False for contact in self.desired_contacts}
        
        # Process all contacts
        for i in range(data.ncon):
            contact = data.contact[i]
            try:
                geom1 = model.geom(contact.geom1).name
                geom2 = model.geom(contact.geom2).name
                
                # Check for desired contacts or their alternatives
                for desired in self.desired_contacts:
                    if geom1 == desired or geom2 == desired:
                        contact_detected[desired] = True
                    else:
                        # Check alternatives
                        alternatives = self.contact_alternatives.get(desired, [])
                        if geom1 in alternatives or geom2 in alternatives:
                            contact_detected[desired] = True
            except Exception as e:
                if self.debug:
                    print(f"Error processing contact: {e}")
                continue
        
        # Count successful contacts
        contact_score = sum(contact_detected.values())
        total_desired = len(self.desired_contacts)
        
        if self.debug:
            print(f"Contact status: {contact_detected}")
            print(f"Contact score: {contact_score}/{total_desired}")
        
        return rewards.tolerance(
            contact_score,
            bounds=(total_desired, total_desired),
            margin=total_desired,
            sigmoid="linear"
        )

# Reward Combinations
@dataclasses.dataclass
class StableStandingReward(humenv_rewards.RewardFunction):
    """Combines multiple rewards for stable standing."""
    standing_weight: float = 0.3
    upright_weight: float = 0.3
    balance_weight: float = 0.2
    control_weight: float = 0.2
    debug: bool = False

    @classmethod
    def reward_from_name(cls, name):
        if name == 'stable-standing':
            return cls()
        return None

    def compute(self, model: mujoco.MjModel, data: mujoco.MjData) -> float:
        # Create reward components with debug setting passed through
        standing_reward = StandingReward()
        upright_reward = UprightReward()
        balance_reward = BalanceReward(debug=self.debug)
        control_reward = SmallControlReward()
        
        # Compute individual rewards
        standing = standing_reward.compute(model, data)
        upright = upright_reward.compute(model, data)
        balance = balance_reward.compute(model, data)
        control = control_reward.compute(model, data)
        
        # Apply weights and combine
        weighted_sum = (
            self.standing_weight * standing +
            self.upright_weight * upright +
            self.balance_weight * balance +
            self.control_weight * control
        )
        
        if self.debug:
            print(f"Stable standing components: standing={standing:.3f}, upright={upright:.3f}, balance={balance:.3f}, control={control:.3f}")
            print(f"Weighted combined reward: {weighted_sum:.3f}")
            
        return weighted_sum

@dataclasses.dataclass
class NaturalWalkingReward(humenv_rewards.RewardFunction):
    """Combines rewards for natural walking motion."""
    balance_weight: float = 0.3
    energy_weight: float = 0.2
    symmetry_weight: float = 0.2
    natural_motion_weight: float = 0.3
    debug: bool = False

    @classmethod
    def reward_from_name(cls, name):
        if name == 'natural-walking':
            return cls()
        return None

    def compute(self, model: mujoco.MjModel, data: mujoco.MjData) -> float:
        # Create reward components with debug setting passed through
        balance_reward = BalanceReward(debug=self.debug)
        energy_reward = EnergyEfficiencyReward()
        symmetry_reward = SymmetryReward(debug=self.debug)
        natural_reward = NaturalMotionReward()
        
        # Compute individual rewards
        balance = balance_reward.compute(model, data)
        energy = energy_reward.compute(model, data)
        symmetry = symmetry_reward.compute(model, data)
        natural = natural_reward.compute(model, data)
        
        # Apply weights and combine
        valid_components = 0
        total_reward = 0
        
        # Only include components with valid data
        if balance > 0 or not self.debug:
            total_reward += self.balance_weight * balance
            valid_components += self.balance_weight
            
        if energy > 0 or not self.debug:
            total_reward += self.energy_weight * energy
            valid_components += self.energy_weight
            
        if symmetry > 0 or not self.debug:
            total_reward += self.symmetry_weight * symmetry
            valid_components += self.symmetry_weight
            
        if natural > 0 or not self.debug:
            total_reward += self.natural_motion_weight * natural
            valid_components += self.natural_motion_weight
        
        # Normalize by valid components to prevent reward collapse when some components fail
        final_reward = total_reward / valid_components if valid_components > 0 else 0.0
        
        if self.debug:
            print(f"Walking components: balance={balance:.3f}, energy={energy:.3f}, symmetry={symmetry:.3f}, natural={natural:.3f}")
            print(f"Weighted combined reward: {final_reward:.3f}")
            
        return final_reward

def print_available_rewards():
    """Print all available reward components and combinations."""
    print("\n=== Basic Reward Components ===")
    basic_rewards = [
        "StandingReward - Maintains target standing height",
        "UprightReward - Maintains upright posture",
        "MovementControlReward - Penalizes excessive movement",
        "SmallControlReward - Penalizes large control inputs",
        "PositionReward - Achieves target position for body parts"
    ]
    for reward in basic_rewards:
        print(f"  - {reward}")

    print("\n=== Advanced Reward Components ===")
    advanced_rewards = [
        "BalanceReward - Maintains balance over support polygon",
        "SymmetryReward - Rewards symmetric postures",
        "EnergyEfficiencyReward - Rewards energy-efficient movements",
        "NaturalMotionReward - Rewards smooth, coordinated movements",
        "GazeDirectionReward - Rewards looking at specific targets",
        "GroundContactReward - Rewards specific contact patterns"
    ]
    for reward in advanced_rewards:
        print(f"  - {reward}")

    print("\n=== Reward Combinations ===")
    combinations = [
        "StableStandingReward - Combined reward for stable standing",
        "NaturalWalkingReward - Combined reward for natural walking"
    ]
    for combo in combinations:
        print(f"  - {combo}") 