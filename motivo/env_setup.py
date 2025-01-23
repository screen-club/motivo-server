import torch
import numpy as np
from humenv import make_humenv
from gymnasium.wrappers import FlattenObservation, TransformObservation, TimeLimit
from gymnasium import Env

class ParameterizedEnv(Env):
    def __init__(self, device="cpu", max_steps=2000000):
        self.env, _ = make_humenv(
            num_envs=1,
            wrappers=[
                FlattenObservation,
                lambda env: TransformObservation(
                    env, 
                    lambda obs: torch.tensor(obs.reshape(1, -1), 
                                          dtype=torch.float32, 
                                          device=device),
                    env.observation_space
                ),
            ],
        )
        
        self.unwrapped_env = self.env.unwrapped
        self.set_default_parameters()
        self.env = TimeLimit(self.env, max_episode_steps=max_steps)

        # Copy properties from wrapped env
        self.action_space = self.env.action_space
        self.observation_space = self.env.observation_space
        self.metadata = self.env.metadata

    def reset(self, **kwargs):
        """Delegate reset to wrapped env"""
        return self.env.reset(**kwargs)

    def step(self, action):
        """Delegate step to wrapped env"""
        return self.env.step(action)

    def render(self):
        """Delegate render to wrapped env"""
        return self.env.render()

    def close(self):
        """Delegate close to wrapped env"""
        return self.env.close()

    @property
    def unwrapped(self):
        """Property to maintain compatibility with gym's unwrapped interface"""
        return self.unwrapped_env

    def set_default_parameters(self):
        """Set default physics parameters"""
        self.parameters = {
            'gravity': -9.81,
            'density': 1.2,
            'wind_x': 0.0,
            'wind_y': 0.0,
            'wind_z': 0.0,
            'viscosity': 0.0,
            'integrator': 0,
            'timestep': 0.002
        }
        self.update_parameters(self.parameters)
        
        # Make floor effectively infinite by increasing its size
        if hasattr(self.unwrapped_env, 'model'):
            # Increase the size of the floor plane (e.g., 1000x1000 units)
            self.unwrapped_env.model.geom_size[0][0] = 500.0  # Half-length in x direction
            self.unwrapped_env.model.geom_size[0][1] = 500.0  # Half-length in y direction

    def update_parameters(self, new_params):
        """Update environment parameters in real-time"""
        # Update internal parameter storage
        self.parameters.update(new_params)
        
        # Apply parameters to environment
        if 'gravity' in new_params:
            self.unwrapped_env.model.opt.gravity[2] = self.parameters['gravity']
        
        self.unwrapped_env.model.opt.density = self.parameters['density']
        self.unwrapped_env.model.opt.wind = np.array([
            self.parameters['wind_x'],
            self.parameters['wind_y'],
            self.parameters['wind_z']
        ])
        self.unwrapped_env.model.opt.viscosity = self.parameters['viscosity']
        self.unwrapped_env.model.opt.integrator = self.parameters['integrator']
        self.unwrapped_env.model.opt.timestep = self.parameters['timestep']

    def get_parameters(self):
        """Get current parameter values"""
        return self.parameters

def setup_environment(device="cpu", max_steps=2000000):
    """Setup parameterized environment with humanoid"""
    return ParameterizedEnv(device=device, max_steps=max_steps) 