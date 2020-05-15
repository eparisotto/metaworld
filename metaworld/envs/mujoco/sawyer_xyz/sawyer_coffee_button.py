import numpy as np
from gym.spaces import Box

from metaworld.envs.env_util import get_asset_full_path
from metaworld.envs.mujoco.sawyer_xyz.base import SawyerXYZEnv


class SawyerCoffeeButtonEnv(SawyerXYZEnv):

    def __init__(self, random_init=False):

        hand_low = (-0.5, 0.40, 0.05)
        hand_high = (0.5, 1, 0.5)
        obj_low = (-0.1, 0.8, 0.28)
        obj_high = (0.1, 0.9, 0.28)

        super().__init__(
            self.model_name,
            hand_low=hand_low,
            hand_high=hand_high,
        )

        self.random_init = random_init

        self.init_config = {
            'obj_init_pos': np.array([0, 0.9, 0.28]),
            'obj_init_angle': 0.3,
            'hand_init_pos': np.array([0., .6, .2]),
        }
        self.goal = np.array([0, 0.78, 0.33])
        self.obj_init_pos = self.init_config['obj_init_pos']
        self.obj_init_angle = self.init_config['obj_init_angle']
        self.hand_init_pos = self.init_config['hand_init_pos']
        goal_low = self.hand_low
        goal_high = self.hand_high

        self.max_path_length = 150

        self.action_space = Box(
            np.array([-1, -1, -1, -1]),
            np.array([1, 1, 1, 1]),
        )

        self.obj_and_goal_space = Box(
            np.array(obj_low),
            np.array(obj_high),
        )
        self.goal_space = Box(np.array(goal_low), np.array(goal_high))
        self.observation_space = Box(
            np.hstack((self.hand_low, obj_low,)),
            np.hstack((self.hand_high, obj_high,)),
        )

        self.reset()

    @property
    def model_name(self):
        return get_asset_full_path('sawyer_xyz/sawyer_coffee.xml')

    def step(self, action):
        self.set_xyz_action(action[:3])
        self.do_simulation([action[-1], -action[-1]])
        # The marker seems to get reset every time you do a simulation
        self._set_goal_marker(self._state_goal)
        ob = self._get_obs()
        obs_dict = self._get_obs_dict()
        reward, reachDist, pushDist = self.compute_reward(action, obs_dict)
        self.curr_path_length += 1
        info = {'reachDist': reachDist, 'goalDist': pushDist, 'epRew' : reward, 'pickRew':None, 'success': float(pushDist <= 0.02)}
        info['goal'] = self.goal

        return ob, reward, False, info

    def _get_obs(self):
        hand = self.get_endeff_pos()
        objPos =  self.data.site_xpos[self.model.site_name2id('buttonStart')]
        flat_obs = np.concatenate((hand, objPos))

        return np.concatenate([flat_obs,])

    def _get_obs_dict(self):
        hand = self.get_endeff_pos()
        objPos =  self.data.site_xpos[self.model.site_name2id('buttonStart')]
        flat_obs = np.concatenate((hand, objPos))
        return dict(
            state_observation=flat_obs,
            state_desired_goal=self._state_goal,
            state_achieved_goal=objPos,
        )

    def _set_goal_marker(self, goal):
        self.data.site_xpos[self.model.site_name2id('coffee_goal')] = (
            goal[:3]
        )

    def reset_model(self):
        self._reset_hand()
        self._state_goal = self.goal.copy()
        self.obj_init_pos = self.init_config['obj_init_pos']
        self.obj_init_angle = self.init_config['obj_init_angle']
        self.objHeight = self.data.get_geom_xpos('objGeom')[2]
        obj_pos = self.obj_init_pos + np.array([0, -0.1, -0.28])

        if self.random_init:
            goal_pos = self.np_random.uniform(
                self.obj_and_goal_space.low,
                self.obj_and_goal_space.high,
                size=(self.obj_and_goal_space.low.size),
            )
            self.obj_init_pos = goal_pos
            button_pos = goal_pos + np.array([0., -0.12, 0.05])
            obj_pos = goal_pos + np.array([0, -0.1, -0.28])
            self._state_goal = button_pos

        self.sim.model.body_pos[self.model.body_name2id('coffee_machine')] = self.obj_init_pos
        self.sim.model.body_pos[self.model.body_name2id('button')] = self._state_goal
        self._set_obj_xyz(obj_pos)
        self._state_goal = self.get_site_pos('coffee_goal')
        self.maxDist = np.abs(self.data.site_xpos[self.model.site_name2id('buttonStart')][1] - self._state_goal[1])
        self.target_reward = 1000*self.maxDist + 1000*2
        return self._get_obs()

    def _reset_hand(self):
        for _ in range(10):
            self.data.set_mocap_pos('mocap', self.hand_init_pos)
            self.data.set_mocap_quat('mocap', np.array([1, 0, 1, 0]))
            self.do_simulation([-1,1], self.frame_skip)

        rightFinger, leftFinger = self.get_site_pos('rightEndEffector'), self.get_site_pos('leftEndEffector')
        self.init_fingerCOM  =  (rightFinger + leftFinger)/2
        self.reachCompleted = False

    def compute_reward(self, actions, obs):
        del actions

        obs = obs['state_observation']

        objPos = obs[3:6]

        leftFinger = self.get_site_pos('leftEndEffector')
        fingerCOM  =  leftFinger

        pressGoal = self._state_goal[1]

        pressDist = np.abs(objPos[1] - pressGoal)
        reachDist = np.linalg.norm(objPos - fingerCOM)

        c1 = 1000
        c2 = 0.01
        c3 = 0.001
        if reachDist < 0.05:
            pressRew = 1000*(self.maxDist - pressDist) + c1*(np.exp(-(pressDist**2)/c2) + np.exp(-(pressDist**2)/c3))
        else:
            pressRew = 0

        pressRew = max(pressRew, 0)
        reward = -reachDist + pressRew

        return [reward, reachDist, pressDist]
