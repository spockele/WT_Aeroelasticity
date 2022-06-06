import numpy as np
import scipy.integrate as spig
import matplotlib.pyplot as plt
import time


relaxation = 1
rho = 1.225
p_atm = 101325

ct_steps = ((.5, .4), (.9, -.4), (.2, .9), (1.1, -.7),)
ct_sins = ((.5, .5), (.9, .3), (.2, .7),)

u_inf_steps = ((1., .5), (1., -.3), (1., .2), (1., -.1))
u_inf_sins = ((1., .5), (.7, .3), (1.2, .5))


class DU95W150:
    def __init__(self):
        data = read_from_file('DU95W150.csv')
        self.alpha_lst = data[:, 0]
        self.cl_lst = data[:, 1]
        self.cd_lst = data[:, 2]
        self.cm_lst = data[:, 3]

    def cl(self, alpha): return np.interp(alpha, self.alpha_lst, self.cl_lst)

    def cd(self, alpha): return np.interp(alpha, self.alpha_lst, self.cd_lst)

    def cm(self, alpha): return np.interp(alpha, self.alpha_lst, self.cm_lst)

    def plot_polars(self):
        fig, axes = plt.subplots(1, 3, figsize=(9, 3.5))
        axes[0].plot(self.alpha_lst[np.logical_and(self.alpha_lst >= -6, self.alpha_lst <= 12)],
                     self.cl_lst[np.logical_and(self.alpha_lst >= -6, self.alpha_lst <= 12)], 'k')
        axes[1].plot(self.cd_lst[np.logical_and(self.alpha_lst >= -6, self.alpha_lst <= 12)],
                     self.cl_lst[np.logical_and(self.alpha_lst >= -6, self.alpha_lst <= 12)], 'k')
        axes[2].plot(self.alpha_lst[np.logical_and(self.alpha_lst >= -6, self.alpha_lst <= 12)],
                     self.cl_lst[np.logical_and(self.alpha_lst >= -6, self.alpha_lst <= 12)] /
                     self.cd_lst[np.logical_and(self.alpha_lst >= -6, self.alpha_lst <= 12)], 'k')

        optimal = np.argmax(self.cl_lst[np.logical_and(self.alpha_lst >= -6, self.alpha_lst <= 12)] /
                            self.cd_lst[np.logical_and(self.alpha_lst >= -6, self.alpha_lst <= 12)])

        axes[0].plot(self.alpha_lst[np.logical_and(self.alpha_lst >= -6, self.alpha_lst <= 12)][optimal],
                     self.cl_lst[np.logical_and(self.alpha_lst >= -6, self.alpha_lst <= 12)][optimal], 'ro')
        axes[1].plot(self.cd_lst[np.logical_and(self.alpha_lst >= -6, self.alpha_lst <= 12)][optimal],
                     self.cl_lst[np.logical_and(self.alpha_lst >= -6, self.alpha_lst <= 12)][optimal], 'ro')
        axes[2].plot(self.alpha_lst[np.logical_and(self.alpha_lst >= -6, self.alpha_lst <= 12)][optimal],
                     self.cl_lst[np.logical_and(self.alpha_lst >= -6, self.alpha_lst <= 12)][optimal] /
                     self.cd_lst[np.logical_and(self.alpha_lst >= -6, self.alpha_lst <= 12)][optimal], 'ro')

        axes[0].set_xlabel('$\\alpha$ ($^{\\circ}$)')
        axes[2].set_xlabel('$\\alpha$ ($^{\\circ}$)')
        axes[1].set_xlabel('$C_d$ (-)')

        axes[0].set_ylabel('$C_l$ ($^{\\circ}$)')
        # axes[1].set_ylabel('$C_l$ ($^{\\circ}$)')
        axes[2].set_ylabel('$C_l/C_d$ (-)')
        fig.set_tight_layout(True)
        plt.savefig('airfoil_polars.pdf')
        plt.show()
        print(self.alpha_lst[np.logical_and(self.alpha_lst >= -6, self.alpha_lst <= 12)][optimal])


class BladeElement: #one of blade elements, the self.r stores radial position in 
#the blade element function 
    def __init__(self, pos_r: float, chord: float, twist: float, airfoil):
        # Fixed values
        self.r = pos_r
        self.c = chord
        self.twist = twist
        # Values to be determined with other functions
        self.a = None
        self.axial_induction = None
        self.azimuthal_induction = None
        self.phi = None
        self.alpha = None
        self.p_n = None
        self.p_t = None
        self.u_tangential = None
        self.u_normal = None

        self.af = airfoil
        self.airfoil = airfoil()

    def __repr__(self): # print blade element
        return f"<Blade Element at r={self.r}, c={self.c}, beta={self.twist}>"

    def determine_loads(self, v_0, omega, pitch, b, r_blade, r_root, yaw=0, azimuth=0, loss=True):
        # bem code for a single blade element, loss is for tip/root loss
        yaw = np.radians(yaw)
        azimuth = np.radians(azimuth)
        # Set initial loop values
        self.a = 0
        error_a = 1
        i = 0
        # Iterative solver for a and a_prime until the difference between the iterations becomes very small
        while True:
            self.u_tangential = omega * self.r # * (1 + self.a_prime)
            self.u_normal = v_0 * (1 - self.a)

            # For the previous a and a_prime, find the flow angle and angle of attack
            self.phi = np.arctan2(self.u_normal, self.u_tangential)
            self.alpha = np.degrees(self.phi) - self.twist - pitch

            # With the angle of attack, determine the lift and drag coefficient from airfoil data interpolation
            cl = self.airfoil.cl(self.alpha)
            cd = self.airfoil.cd(self.alpha)

            # Use these to find the normal and tangential force coefficients
            cn = cl * np.cos(self.phi) + cd * np.sin(self.phi)
            ct = cl * np.sin(self.phi) - cd * np.cos(self.phi)

            # Break conditions for the a-loop
            if error_a <= 1e-9: # and error_a_dash <= 1e-9:
                break
            elif i > 1e3:
                raise ValueError(f"r={self.r}: Solution for a not converging. a={self.a}.")

            # Determine the solidity and Prandtl’s tip loss correction
            solidity = self.c * b / (2 * np.pi * self.r)
            f_tip = (2/np.pi) * np.arccos(np.exp(-(b * (r_blade - self.r) / (2 * self.r * np.sin(abs(self.phi)))))) if loss else 1
            f_root = (2 / np.pi) * np.arccos(np.exp(-(b * (self.r - r_root) / (2 * self.r * np.sin(abs(self.phi))))))
            f = f_root * f_tip

            # Determine the new a and a_prime
            # If it's higher than 0.33, use a glauert correction
            if self.a >= 0.33:
                c_thrust = ((1 - self.a) ** 2 * cn * solidity) / (np.sin(self.phi) ** 2)

                a_star = c_thrust / (4 * f * (1 - 0.25*(5 - 3 * self.a) * self.a))
                a_new = relaxation * a_star + (1-relaxation) * self.a

            else:
                a_new = 1 / ((4 * f * np.sin(self.phi)**2) / (solidity * cn) + 1)

            # Determine the difference between this and the previous iteration
            error_a = abs(a_new - self.a)

            # Get ready for the next iteration
            self.a = a_new
            i += 1

        self.p_n, self.p_t, _, _ = loads(self.a, self.r, self.twist, self.c, r_blade, pitch, self.airfoil,
                                         v_0, omega, yaw, azimuth)

    def get_loads(self):
        if self.p_t is None or self.p_n is None:
            raise ValueError(f"Loads have not been determined. Run .determine_loads() first.")
        else:
            return self.p_n, self.p_t

    def reset(self):
        self.__init__(self.r, self.c, self.twist, self.af)


class Blade:
    def __init__(self, n_blades, airfoil, r_start, r_end, blade_pitch, n_elements):
        self.b = n_blades

        self.power = None
        self.thrust = None
        self.c_power = None
        self.c_thrust = None

        self.r_list = []
        self.p_n_list = None
        self.p_t_list = None

        self.blade_elements = list()

        # Divide the blade up in n_elements pieces;
        for i in range(n_elements + 1):
            r = r_start + (r_end - r_start)/n_elements * i
            self.r_list.append(r)
            # Sorry for hardcoding the equations below- taken from the assignment description :)
            twist = 14*(1-r/r_end)
            chord = (3*(1-r/r_end)+1)

            # BladeElement takes in argument relative_pitch, I assume that this means total? So offset with the blade pitch
            relative_pitch = blade_pitch + twist

            self.blade_elements.append(BladeElement(r, chord, relative_pitch, airfoil))

        self.r_list = np.array(self.r_list)
        self.r = r_end

    def find_pn_pt(self, v_0, pitch, omega, yaw=0, azimuth=0, loss=True):
        # Initialise the lists for p_n and p_t
        p_n_list, p_t_list = list(), list()
        for blade_element in self.blade_elements:
            if self.r_list[0] < blade_element.r < self.r:
                blade_element.determine_loads(v_0, omega, pitch, self.b, self.r, self.r_list[0], yaw, azimuth, loss)
                p_n, p_t = blade_element.get_loads()

                p_n_list.append(p_n)
                p_t_list.append(p_t)

            else:
                # Add zero load at the blade tip and root
                p_n_list.append(0)
                p_t_list.append(0)

        return np.array(p_n_list), np.array(p_t_list), self.r_list

    def determine_cp_ct(self, v_0, tsr, pitch, yaw=0, azimuth=0, loss=True):
        """
        Let the BEM code Determine the power and thrust coefficient of the turbine
        :param v_0: Incoming velocity
        :param tsr: Tip speed ratio
        :param pitch: pitch angle
        :param yaw: yaw angle
        :param azimuth: azimuthal position in the turbine disk
        :param loss: turn on or off the tip loss factor
        :return: None
        """
        # Reset the blade s.t. the code is a touch faster.
        self.reset()
        # Determine the rotational speed of the turbine
        omega = tsr * v_0 / self.r
        # Get the loads on the blade elements
        self.p_n_list, self.p_t_list, r_list = self.find_pn_pt(v_0, pitch, omega, yaw, azimuth, loss)

        # Determine the thrust and power of the turbine
        self.thrust = self.b * spig.trapz(self.p_n_list, self.r_list)
        self.power = omega * self.b * spig.trapz(self.p_t_list * self.r_list, self.r_list)

        # Determine the thrust and power coefficient
        self.c_thrust = self.thrust / (0.5 * rho * np.pi * self.r**2 * v_0**2)
        self.c_power = self.power / (0.5 * rho * np.pi * self.r**2 * v_0**3)

    def reset(self):
        for be in self.blade_elements:
            be.reset()


class Turbine:
    def __init__(self, n_annuli):
        self.blade = Blade(3, DU95W150, .2 * 50, 50, -2, n_annuli)

    def ct_pitch(self, v0, tsr):
        """
        Determine the thrust coefficient vs. thrust curve
        :param v0: The incoming velocity
        :param tsr: The turbine tip-speed ratio
        :return: None
        """
        pitch = np.round(np.arange(-10, 15 + .01, .01), 2)
        ct = np.empty(pitch.shape)
        for i, theta in enumerate(pitch):
            print(theta)
            self.blade.determine_cp_ct(v0, tsr, theta)
            ct[i] = self.blade.c_thrust

        out_array = np.array([pitch, ct])
        write_to_file(out_array, f'ct_pitch_{v0}_{tsr}.csv')

    @staticmethod
    def pitch(ct_in, v0, tsr):
        """
        Determine the pitch required to achieve a given thrust coefficient
        MAKE SURE TO HAVE THE THRUST-PITCH CURVE DETERMINED USING ct_pitch()
        :param ct_in: Input thrust coefficient
        :param v0: The incoming velocity
        :param tsr: The turbine tip-speed ratio
        :return: The pitch angle in degrees
        """
        pitch, ct = read_from_file(f'ct_pitch_{v0}_{tsr}.csv')

        ct1, ct2 = ct[ct > ct_in][-1], ct[ct <= ct_in][0]
        pitch1, pitch2 = pitch[ct > ct_in][-1], pitch[ct <= ct_in][0]

        return interpolate(pitch1, pitch2, ct1, ct2, ct_in)

    def u_inf_func(self, u_inf_0, delta_u_inf, reduced_freq, v0, tsr, model='pp'):
        """
        Determine and plot the time evolution of the turbine properties given a step in thrust coefficient
        :param u_inf_0: Mean inflow velocity
        :param delta_u_inf: Amplitude of the inflow velocity variation
        :param reduced_freq: Reduced frequency of the dynamic inflow
        :param v0: The incoming velocity
        :param tsr: The turbine tip-speed ratio
        :param model: Selection of the dynamic inflow model (pp: Pitt-Peters, lm: Larsen-Madsen, oye: Oye)
        :return: None
        """
        if model not in ('pp', 'lm', 'oye'):
            raise ValueError("Unknown model, please enter one of the following: 'pp', 'lm', 'oye'.")

        # Initialise a timer list to check compute time
        timer = [time.time(), ]

        # Initialise the time parameters: time step, start and final time
        delta_t = .04 * self.blade.r / v0
        t_0 = -.2 * self.blade.r / v0
        t_final = 10 * self.blade.r / v0 if reduced_freq is None else 4 * np.pi / reduced_freq * self.blade.r / v0
        t_list = np.round(np.arange(t_0, t_final + delta_t, delta_t), 9)

        # Extract the radial positions of the blade elements and the radial length of each
        r_list = self.blade.r_list[1:-1]
        dr = r_list[1] - r_list[0]

        # Set the ct and pitch time series depending on whether the case is a step function or a sinusoidal function
        if reduced_freq is None:
            # In case of a step function, start with an empty array for both ct and pitch
            u_inf = np.empty((t_list.size,))

            # Fill all the values before t=0 with the initial ct and the corresponding pitch
            u_inf[t_list <= 0] = u_inf_0
            # Fill all the values after t=0 with the final ct and the corresponding pitch
            u_inf[t_list > 0] = u_inf_0 + delta_u_inf / v0
        else:
            # In case of a sinusoidal function, generate the sinusoid and determine the corresponding pitch time series
            u_inf = u_inf_0 + delta_u_inf / v0 * np.sin(reduced_freq * v0 / self.blade.r * t_list)

        u_inf *= v0

        # Initialise the output value arrays: induction, AoA, thrust coefficient.
        # The shape is (time series x spanwise distribution).
        a = np.empty((t_list.size, r_list.size))
        alpha = np.empty((t_list.size, r_list.size))
        phi = np.empty((t_list.size, r_list.size))
        ctr = np.empty((t_list.size, r_list.size))
        cqr = np.empty((t_list.size, r_list.size))

        # Initialise the intermediate induced velocity array.
        # The shape is (time series x spanwise distribution).
        v_int = np.empty((t_list.size, r_list.size))

        # Initialise the quasi-steady value arrays: induction, AoA, thrust coefficient.
        # The shape is (time series x spanwise distribution).
        a_qs = np.empty((t_list.size, r_list.size))
        alpha_qs = np.empty((t_list.size, r_list.size))
        phi_qs = np.empty((t_list.size, r_list.size))
        ctr_qs = np.empty((t_list.size, r_list.size))
        cqr_qs = np.empty((t_list.size, r_list.size))

        # Loop over time, with index 'n' and time 't'
        for n, t in enumerate(t_list):
            # Just some stuff to print the status every once in a while and to monitor compute time.
            if not n:
                print(f't = {t}s\t\t(t_final = {round(t_final, 1)}s)\t(Preparation computed in {round(time.time() - timer[-1], 3)} s)')
                timer.append(time.time())
            elif t % 5 == 0:
                print(f't = {t}s\t\t(t_final = {round(t_final, 1)}s)\t(Last 5 seconds computed in {round(time.time() - timer[-1], 3)} s)')
                timer.append(time.time())

            # Some stuff for efficiency
            # In case the pitch does not change (I used this check because there sometimes is a machine error here)
            # Also ensure the first time step gets correct values by ignoring it in this check with the 2nd condition
            if abs(u_inf[n] - u_inf[n - 1]) < 1e-15 and n != 0:
                # Just reuse the thrust coefficient distribution from the previous time step
                ctr_qs[n, :] = ctr_qs[n - 1, :]
                cqr_qs[n, :] = cqr_qs[n - 1, :]

            # In case the pitch has changed since last time step
            else:
                # Run the BEM code for this pitch angle
                self.blade.reset()
                self.blade.determine_cp_ct(u_inf[n], tsr * v0 / u_inf[n], 0)
                # Get the new qs thrust coefficient distribution
                ctr_qs[n, :] = c_thrust(self.blade.p_n_list[1:-1], u_inf[n], r_list, self.blade.b, dr)
                cqr_qs[n, :] = c_thrust(self.blade.p_t_list[1:-1], u_inf[n], r_list, self.blade.b, dr) * r_list / self.blade.r

            # Loop over the blade elements
            for i, be in enumerate(self.blade.blade_elements[1:-1]):
                # Set a tuple with parameters that the loads() function will need inside the different models
                params = (be.r, be.twist, be.c, self.blade.r, 0, be.airfoil, u_inf[n], tsr * v0 / self.blade.r, 0, 0)

                a_qs[n, i] = be.a
                alpha_qs[n, i] = be.alpha
                phi_qs[n, i] = be.phi

                # At the first time step, just initialise the output and intermediate value arrays
                if n == 0:
                    a[0, i] = be.a
                    pn, pt, alpha[0, i], phi[0, i] = loads(a[0, i], *params)
                    ctr[0, i] = c_thrust(pn, u_inf[n], be.r, self.blade.b, dr)
                    cqr[0, i] = c_thrust(pt, u_inf[n], be.r, self.blade.b, dr) * be.r / self.blade.r
                    v_int[0, i] = -a[0, i] * v0

                # If the model is Pitt-Peters
                elif model == 'pp':
                    # Propagate the AoA and induction factor of this blade element with pitt_peters()
                    a[n, i] = pitt_peters(ctr_qs[n, i], a[n - 1, i], delta_t, params, dr, self.blade.b)

                # In case of Larsen-Madsen
                elif model == 'lm':
                    # Propagate the AoA and induction factor of this blade element with larsen_madsen().
                    # be.a is the quasi-steady induction factor that L-M requires
                    a[n, i] = larsen_madsen(be.a, a[n - 1, i], delta_t, params)

                elif model == 'oye':
                    # Propagate the AoA and induction factor of this blade element with oye().
                    a[n, i], v_int[n, i] = oye(a_qs[n, i], a_qs[n - 1, i], a[n - 1, i], delta_t, params,
                                               v_int[n - 1, i])

                pn, pt, alpha[n, i], phi[n, i] = loads(a[n, i], *params)
                ctr[n, i] = c_thrust(pn, u_inf[n], be.r, self.blade.b, dr)
                cqr[n, i] = c_thrust(pt, u_inf[n], be.r, self.blade.b, dr) * be.r / self.blade.r

        # Just a happy print statement bacause the code is done running :D
        print(f'Done! (Entire time series computed in {round(timer[-1] - timer[0], 3)} s)')

        # Return the outputs for later plotting
        return r_list, t_list, ctr, cqr, a, alpha, phi, ctr_qs, cqr_qs, a_qs, alpha_qs, phi_qs

    def ct_func(self, ct0, delta_ct, reduced_freq, v0, tsr, model='pp'):
        """
        Determine and plot the time evolution of the turbine properties given a step in thrust coefficient
        :param ct0: Mean thrust coefficient
        :param delta_ct: Amplitude of the thrust coefficient variation
        :param reduced_freq: Reduced frequency of the dynamic inflow
        :param v0: The incoming velocity
        :param tsr: The turbine tip-speed ratio
        :param model: Selection of the dynamic inflow model (pp: Pitt-Peters, lm: Larsen-Madsen, oye: Oye)
        :return: None
        """
        if model not in ('pp', 'lm', 'oye'):
            raise ValueError("Unknown model, please enter one of the following: 'pp', 'lm', 'oye'.")

        # Initialise a timer list to check compute time
        timer = [time.time(), ]

        # Initialise the time parameters: time step, start and final time
        delta_t = .04 * self.blade.r / v0
        t_0 = -.2 * self.blade.r / v0
        t_final = 10 * self.blade.r / v0 if reduced_freq is None else 4 * np.pi / reduced_freq * self.blade.r / v0
        t_list = np.round(np.arange(t_0, t_final + delta_t, delta_t), 9)

        # Extract the radial positions of the blade elements and the radial length of each
        r_list = self.blade.r_list[1:-1]
        dr = r_list[1] - r_list[0]

        # Set the ct and pitch time series depending on whether the case is a step function or a sinusoidal function
        if reduced_freq is None:
            # In case of a step function, start with an empty array for both ct and pitch
            ct, pitch = np.empty((2, t_list.size))

            # Fill all the values before t=0 with the initial ct and the corresponding pitch
            ct[t_list <= 0] = ct0
            pitch[t_list <= 0] = self.pitch(ct0, v0, tsr)
            # Fill all the values after t=0 with the final ct and the corresponding pitch
            ct[t_list > 0] = ct0 + delta_ct
            pitch[t_list > 0] = self.pitch(ct0 + delta_ct, v0, tsr)
        else:
            # In case of a sinusoidal function, generate the sinusoid and determine the corresponding pitch time series
            ct = ct0 + delta_ct * np.sin(reduced_freq * v0 / self.blade.r * t_list)
            pitch = np.array([self.pitch(ctn, v0, tsr) for ctn in ct])

        # Initialise the output value arrays: induction, AoA, thrust coefficient.
        # The shape is (time series x spanwise distribution).
        a = np.empty((t_list.size, r_list.size))
        alpha = np.empty((t_list.size, r_list.size))
        phi = np.empty((t_list.size, r_list.size))
        ctr = np.empty((t_list.size, r_list.size))
        cqr = np.empty((t_list.size, r_list.size))

        # Initialise the intermediate induced velocity array.
        # The shape is (time series x spanwise distribution).
        v_int = np.empty((t_list.size, r_list.size))

        # Initialise the quasi-steady value arrays: induction, AoA, thrust coefficient.
        # The shape is (time series x spanwise distribution).
        a_qs = np.empty((t_list.size, r_list.size))
        alpha_qs = np.empty((t_list.size, r_list.size))
        phi_qs = np.empty((t_list.size, r_list.size))
        ctr_qs = np.empty((t_list.size, r_list.size))
        cqr_qs = np.empty((t_list.size, r_list.size))

        # Loop over time, with index 'n' and time 't'
        for n, t in enumerate(t_list):
            # Just some stuff to print the status every once in a while and to monitor compute time.
            if not n:
                print(f't = {t}s\t\t(t_final = {round(t_final, 1)}s)\t(Preparation computed in {round(time.time() - timer[-1], 3)} s)')
                timer.append(time.time())
            elif t % 5 == 0:
                print(f't = {t}s\t\t(t_final = {round(t_final, 1)}s)\t(Last 5 seconds computed in {round(time.time() - timer[-1], 3)} s)')
                timer.append(time.time())

            # Some stuff for efficiency
            # In case the pitch does not change (I used this check because there sometimes is a machine error here)
            # Also ensure the first time step gets correct values by ignoring it in this check with the 2nd condition
            if abs(pitch[n] - pitch[n-1]) < 1e-15 and n != 0:
                # Just reuse the thrust coefficient distribution from the previous time step
                ctr_qs[n, :] = ctr_qs[n - 1, :]
                cqr_qs[n, :] = cqr_qs[n - 1, :]

            # In case the pitch has changed since last time step
            else:
                # Run the BEM code for this pitch angle to set qs values
                self.blade.reset()
                self.blade.determine_cp_ct(v0, tsr, pitch[n])
                # Get the new qs thrust coefficient distribution
                ctr_qs[n, :] = c_thrust(self.blade.p_n_list[1:-1], v0, r_list, self.blade.b, dr)
                cqr_qs[n, :] = c_thrust(self.blade.p_t_list[1:-1], v0, r_list, self.blade.b, dr) * r_list / self.blade.r

            # Loop over the blade elements
            for i, be in enumerate(self.blade.blade_elements[1:-1]):
                # Set a tuple with parameters that the loads() function will need inside the different models
                params = (be.r, be.twist, be.c, self.blade.r, pitch[n], be.airfoil, v0, tsr * v0 / self.blade.r, 0, 0)

                a_qs[n, i] = be.a
                alpha_qs[n, i] = be.alpha
                phi_qs[n, i] = np.degrees(be.phi)

                # At the first time step, just initialise the output and intermediate value arrays
                if n == 0:
                    a[0, i] = be.a
                    pn, pt, alpha[0, i], phi[0, i] = loads(a[0, i], *params)
                    ctr[0, i] = c_thrust(pn, v0, be.r, self.blade.b, dr)
                    cqr[0, i] = c_thrust(pt, v0, be.r, self.blade.b, dr) * be.r / self.blade.r
                    v_int[0, i] = -a[0, i] * v0

                # If the model is Pitt-Peters
                elif model == 'pp':
                    # Propagate the AoA and induction factor of this blade element with pitt_peters()
                    a[n, i] = pitt_peters(ctr_qs[n, i], a[n-1, i], delta_t, params, dr, self.blade.b)

                # In case of Larsen-Madsen
                elif model == 'lm':
                    # Propagate the AoA and induction factor of this blade element with larsen_madsen().
                    # be.a is the quasi-steady induction factor that L-M requires
                    a[n, i] = larsen_madsen(be.a, a[n-1, i], delta_t, params)

                elif model == 'oye':
                    # Propagate the AoA and induction factor of this blade element with oye().
                    a[n, i], v_int[n, i] = oye(a_qs[n, i], a_qs[n-1, i], a[n-1, i], delta_t, params, v_int[n-1, i])

                pn, pt, alpha[n, i], phi[n, i] = loads(a[n, i], *params)
                ctr[n, i] = c_thrust(pn, v0, be.r, self.blade.b, dr)
                cqr[n, i] = c_thrust(pt, v0, be.r, self.blade.b, dr) * be.r / self.blade.r

        # Just a happy print statement bacause the code is done running :D
        print(f'Done! (Entire time series computed in {round(timer[-1] - timer[0], 3)} s)')

        # Return the outputs for later plotting
        return r_list, t_list, ctr, cqr, a, alpha, phi, ctr_qs, cqr_qs, a_qs, alpha_qs, phi_qs


def c_thrust(p_n, v0, r, b, dr):
    """
    Determine the local thrust coefficient based on the local loading
    :param p_n: Local thrust loading in [N/m]
    :param v0: Turbine incoming velocity
    :param r: Radial position
    :param b: Number of turbine blades
    :param dr: Blade element length
    :return: the local thrust coefficient [-]
    """
    return b * p_n / (.5 * rho * v0 ** 2 * np.pi * r * dr)


def pitt_peters(c_thrust_current, a_previous, dt, be_params, dr, b):
    """
    Calculate the new induction factor using Pitts-Peters
    :param c_thrust_current: Thrust coefficient at this time step
    :param a_previous: Induction factor at previous time step
    :param dt: Time step
    :param be_params: Parameters of the blade element required for the loads() function
        (r, twist, c, r_blade, pitch, airfoil, v_0, omega, yaw, azimuth)
    :param dr: Radial length of the blade element
    :param b: Number of turbine blades
    :return: The current time step: angle of attack, induction factor
    """
    # Determine the thrust loading on the blade element based on the previous time step induction factor
    p_n, _, _, _ = loads(a_previous, *be_params)
    # Use the thrust loading to determine the local thrust coefficient
    c_thrust_ind = c_thrust(p_n, be_params[6], be_params[0], b, dr)
    # print(c_thrust_current - c_thrust_ind)

    # Calculate the time derivative of the induction factor
    da_dt = (c_thrust_current - c_thrust_ind) / (16 / (3 * np.pi)) * (
             be_params[6] ** 2 / be_params[3]) / be_params[6]
    # Calculate the new induction factor with time propagation
    a_current = a_previous - da_dt * dt
    return a_current


def larsen_madsen(a_qs_current, a_previous, dt, be_params):
    """
    Calculate the new induction factor using the Larsen-Madsen model
    :param a_qs_current: Steady-state induction factor at this time step
    :param a_previous: Induction factor at previous time step
    :param dt: Time step
    :param be_params: Parameters of the blade element required for the loads() function
        (r, twist, c, r_blade, pitch, airfoil, v_0, omega, yaw, azimuth)
    :return: The current time step: angle of attack, induction factor
    """
    # # Determine the thrust loading on the blade element based on the previous time step induction factor
    # p_n, _, _ = loads(a_previous, *be_params)
    
    # Evaluate the wake velocity
    v_wake = be_params[6] * (1 - a_previous)
    
    # Evaluate the time scale time scale of the model
    tau = 0.5 * be_params[3] / v_wake
    
    # Evaluate the transient and quasi steady induction factors
    a_transient = a_previous * np.exp(-dt/tau)
    a_quasteady = a_qs_current * (1 - np.exp(-dt/tau))
    
    # Evaluate the new induction factor 
    a_current = a_transient + a_quasteady
    
    # Evaluate the time rate of change of the induction factor
    _ = (a_previous - a_current)/dt
    
    return a_current


def oye(a_qs_current, a_qs_previous, a_previous, dt, be_params, v_int_previous):
    """
    Calculate the new induction factor using the Oye model
    :param a_qs_current: Steady-state induction factor at this time step
    :param a_qs_previous: Steady-state induction factor at previous time step
    :param a_previous: Induction factor at previous time step
    :param dt: Time step
    :param be_params: Parameters of the blade element required for the loads() function
        (r, twist, c, r_blade, pitch, airfoil, v_0, omega, yaw, azimuth)
    :param v_int_previous: intermediate induced velocity at the previous time step
    :return: The current time step: angle of attack, induction factor and intermediate induced velocity
    """
    # # Determine the thrust loading on the blade element based on the previous time step induction factor
    # _, _, alpha = loads(a_previous, *be_params)
    
    # calculate quasi-steady induction velocity
    v_qs_previous = -a_qs_previous * be_params[6]
    # calculate induction velocity of the previous time step
    v_ind_previous = a_previous * be_params[6]

    # calculate time scales of the model
    t1 = 1.1 / (1 - 1.3 * a_previous) * be_params[3] / be_params[6]
    t2 = (0.39 - 0.26 * (be_params[0] / be_params[3])**2) * t1

    # calculate next-time-step quasi-steady induction velocity
    v_qs_current = -a_qs_current * be_params[6]
        
    # calculate time derivative of intermediate velocity
    dvint_dt = (v_qs_previous + (v_qs_current - v_qs_previous) / dt * 0.6 * t1 - v_int_previous) / t1

    # calculate new intermediate velocity
    v_int_current = v_int_previous + dvint_dt * dt
    
    # calculate time derivaive of the induced velocity
    dvz_dt = ((v_int_previous + v_int_current) / 2 + v_ind_previous) / t2
    
    # calculate new induced velocity
    a_current = (v_ind_previous - dvz_dt * dt) / be_params[6]
    return a_current, v_int_current


def xi(a, yaw):
    # Using the approximation given in slides 2.2.2:12.
    return (0.6 * a + 1) * yaw


def loads(a, r, twist, c, r_blade, pitch, airfoil, v_0, omega, yaw, azimuth):
    """
    Determine the local loading based on geometry and induction
    :param a: local induction factor
    :param r: radial position
    :param twist: local blade twist angle in degrees
    :param c: local blade chord
    :param r_blade: blade radius
    :param pitch: global blade pitch
    :param airfoil: the used airfoil
    :param v_0: incoming velocity
    :param omega: turbine rotational speed
    :param yaw: yaw angle in degrees
    :param azimuth: azimuthal position in degrees
    :return: the thrust and power loading
    """
    # Determining skew angle of outgoing flow
    x = xi(a, yaw)

    # Using Coleman's model for vortex cylinder in yaw
    K_xi = 2 * np.tan(x / 2)

    # Using Glauert theory for yawed motion, determine separate induction factors. (slides 2.2.2:9)
    axial_induction = a * (1 + K_xi * r * np.sin(azimuth - np.pi / 2) / r_blade)
    # self.azimuthal_induction = self.a_prime

    u_tangential = (omega * r - v_0 * np.sin(yaw) * np.sin(azimuth)) # * (1 + self.a_prime)
    u_normal = v_0 * (np.cos(yaw) - axial_induction)

    # For the previous a and a_prime, find the flow angle and angle of attack
    phi = np.arctan2(u_normal, u_tangential)
    alpha = np.degrees(phi) - twist - pitch

    # With the angle of attack, determine the lift and drag coefficient from airfoil data interpolation
    cl = airfoil.cl(alpha)
    cd = airfoil.cd(alpha)

    # Use these to find the normal and tangential force coefficients
    cn = cl * np.cos(phi) + cd * np.sin(phi)
    ct = cl * np.sin(phi) - cd * np.cos(phi)

    # Determine the relative velocity with the velocity triangle
    v_rel = np.sqrt(u_normal**2 + u_tangential**2)

    # Using the previous calculations, find the forces on the blade element
    p_n = 0.5 * rho * v_rel ** 2 * c * cn
    p_t = 0.5 * rho * v_rel ** 2 * c * ct

    return p_n, p_t, alpha, np.degrees(phi)


def interpolate(value1, value2, co1, co2, co_interpolation):
    """
    Interpolate linearly between two points
    :param value1: f(x1)
    :param value2: f(x2)
    :param co1: x1
    :param co2: x2
    :param co_interpolation: x
    :return: f(x)
    """
    df_dx = (value2 - value1) / (co2 - co1)
    return df_dx * (co_interpolation - co1) + value1


def write_to_file(array, path):
    """
    Write a 2D array to a file
    :param array: A 2D numpy array of python list
    :param path: The file path to write to
    """
    lines = []
    for row in array:
        line = ''
        for num in row:
            line = line + f'{num},'

        lines.append(line[:-1] + '\n')

    f = open(path, 'w')
    f.writelines(lines)
    f.close()


def read_from_file(path):
    """
    Read a file made with write_to_file(_, path)
    :param path: The file path to read from
    :return: A 2D numpy array with the data in the file
    """
    # Read the file to raw data
    with open(path) as f:
        lines = f.readlines()
    # Read out the raw data
    out_list = [[float(num) for num in line.strip('\n').split(',')] for line in lines]
    # Return as numpy array
    return np.array(out_list)


def generate_data():
    # Create the turbine with 25 blade elements
    turbine = Turbine(25)

    for i, model in enumerate(('pp', 'lm', 'oye')):
        print(f'============== MODEL = {model.upper()} ==============')
        for case in ct_steps:
            print(f'----- ct0 = {case[0]}, d_ct = {case[1]}, rf = {0} -----')
            r_list, t_list, ctr, cqr, a, alpha, phi, ctr_qs, cqr_qs, a_qs, alpha_qs, phi_qs = turbine.ct_func(*case, None, 10, 10, model=model)
            write_to_file([r_list, ], f'./{model}/ct_step/{case[0]}_{case[1]}_r_list.csv')
            write_to_file([t_list, ], f'./{model}/ct_step/{case[0]}_{case[1]}_t_list.csv')
            write_to_file(ctr, f'./{model}/ct_step/{case[0]}_{case[1]}_ctr.csv')
            write_to_file(cqr, f'./{model}/ct_step/{case[0]}_{case[1]}_cqr.csv')
            write_to_file(a, f'./{model}/ct_step/{case[0]}_{case[1]}_a.csv')
            write_to_file(alpha, f'./{model}/ct_step/{case[0]}_{case[1]}_alpha.csv')
            write_to_file(phi, f'./{model}/ct_step/{case[0]}_{case[1]}_phi.csv')
            write_to_file(ctr_qs, f'./{model}/ct_step/{case[0]}_{case[1]}_ctr_qs.csv')
            write_to_file(cqr_qs, f'./{model}/ct_step/{case[0]}_{case[1]}_cqr_qs.csv')
            write_to_file(a_qs, f'./{model}/ct_step/{case[0]}_{case[1]}_a_qs.csv')
            write_to_file(alpha_qs, f'./{model}/ct_step/{case[0]}_{case[1]}_alpha_qs.csv')
            write_to_file(phi_qs, f'./{model}/ct_step/{case[0]}_{case[1]}_phi_qs.csv')
            print()

        for case in ct_sins:
            for rf in np.round(np.arange(0.05, 0.35, 0.05), 2):
                print(f'----- ct0 = {case[0]}, d_ct = {case[1]}, rf = {rf} -----')
                r_list, t_list, ctr, cqr, a, alpha, phi, ctr_qs, cqr_qs, a_qs, alpha_qs, phi_qs = turbine.ct_func(*case, rf, 10, 10, model=model)
                write_to_file([r_list, ], f'./{model}/ct_sin/{case[0]}_{case[1]}_{rf}_r_list.csv')
                write_to_file([t_list, ], f'./{model}/ct_sin/{case[0]}_{case[1]}_{rf}_t_list.csv')
                write_to_file(ctr, f'./{model}/ct_sin/{case[0]}_{case[1]}_{rf}_ctr.csv')
                write_to_file(cqr, f'./{model}/ct_sin/{case[0]}_{case[1]}_{rf}_cqr.csv')
                write_to_file(a, f'./{model}/ct_sin/{case[0]}_{case[1]}_{rf}_a.csv')
                write_to_file(alpha, f'./{model}/ct_sin/{case[0]}_{case[1]}_{rf}_alpha.csv')
                write_to_file(phi, f'./{model}/ct_sin/{case[0]}_{case[1]}_{rf}_phi.csv')
                write_to_file(ctr_qs, f'./{model}/ct_sin/{case[0]}_{case[1]}_{rf}_ctr_qs.csv')
                write_to_file(cqr_qs, f'./{model}/ct_sin/{case[0]}_{case[1]}_{rf}_cqr_qs.csv')
                write_to_file(a_qs, f'./{model}/ct_sin/{case[0]}_{case[1]}_{rf}_a_qs.csv')
                write_to_file(alpha_qs, f'./{model}/ct_sin/{case[0]}_{case[1]}_{rf}_alpha_qs.csv')
                write_to_file(phi_qs, f'./{model}/ct_sin/{case[0]}_{case[1]}_{rf}_phi_qs.csv')
                print()

        for case in u_inf_steps:
            print(f'----- u0 = {case[0]}, d_u = {case[1]}, rf = {0} -----')
            r_list, t_list, ctr, cqr, a, alpha, phi, ctr_qs, cqr_qs, a_qs, alpha_qs, phi_qs = turbine.u_inf_func(*case, None, 10, 10, model=model)
            write_to_file([r_list, ], f'./{model}/u_inf_step/{case[0]}_{case[1]}_r_list.csv')
            write_to_file([t_list, ], f'./{model}/u_inf_step/{case[0]}_{case[1]}_t_list.csv')
            write_to_file(ctr, f'./{model}/u_inf_step/{case[0]}_{case[1]}_ctr.csv')
            write_to_file(cqr, f'./{model}/u_inf_step/{case[0]}_{case[1]}_cqr.csv')
            write_to_file(a, f'./{model}/u_inf_step/{case[0]}_{case[1]}_a.csv')
            write_to_file(alpha, f'./{model}/u_inf_step/{case[0]}_{case[1]}_alpha.csv')
            write_to_file(phi, f'./{model}/u_inf_step/{case[0]}_{case[1]}_phi.csv')
            write_to_file(ctr_qs, f'./{model}/u_inf_step/{case[0]}_{case[1]}_ctr_qs.csv')
            write_to_file(cqr_qs, f'./{model}/u_inf_step/{case[0]}_{case[1]}_cqr_qs.csv')
            write_to_file(a_qs, f'./{model}/u_inf_step/{case[0]}_{case[1]}_a_qs.csv')
            write_to_file(alpha_qs, f'./{model}/u_inf_step/{case[0]}_{case[1]}_alpha_qs.csv')
            write_to_file(phi_qs, f'./{model}/u_inf_step/{case[0]}_{case[1]}_phi_qs.csv')
            print()

        for case in u_inf_sins:
            for rf in np.round(np.arange(0.05, 0.35, 0.05), 2):
                print(f'----- u0 = {case[0]}, d_u = {case[1]}, rf = {rf} -----')
                try:
                    r_list, t_list, ctr, cqr, a, alpha, phi, ctr_qs, cqr_qs, a_qs, alpha_qs, phi_qs = turbine.u_inf_func(*case, rf, 10, 10, model=model)
                except ValueError:
                    global relaxation
                    relaxation = .25
                    r_list, t_list, ctr, cqr, a, alpha, phi, ctr_qs, cqr_qs, a_qs, alpha_qs, phi_qs = turbine.u_inf_func(*case, rf, 10, 10, model=model)
                    relaxation = 1

                write_to_file([r_list, ], f'./{model}/u_inf_sin/{case[0]}_{case[1]}_{rf}_r_list.csv')
                write_to_file([t_list, ], f'./{model}/u_inf_sin/{case[0]}_{case[1]}_{rf}_t_list.csv')
                write_to_file(ctr, f'./{model}/u_inf_sin/{case[0]}_{case[1]}_{rf}_ctr.csv')
                write_to_file(cqr, f'./{model}/u_inf_sin/{case[0]}_{case[1]}_{rf}_cqr.csv')
                write_to_file(a, f'./{model}/u_inf_sin/{case[0]}_{case[1]}_{rf}_a.csv')
                write_to_file(alpha, f'./{model}/u_inf_sin/{case[0]}_{case[1]}_{rf}_alpha.csv')
                write_to_file(phi, f'./{model}/u_inf_sin/{case[0]}_{case[1]}_{rf}_phi.csv')
                write_to_file(ctr_qs, f'./{model}/u_inf_sin/{case[0]}_{case[1]}_{rf}_ctr_qs.csv')
                write_to_file(cqr_qs, f'./{model}/u_inf_sin/{case[0]}_{case[1]}_{rf}_cqr_qs.csv')
                write_to_file(a_qs, f'./{model}/u_inf_sin/{case[0]}_{case[1]}_{rf}_a_qs.csv')
                write_to_file(alpha_qs, f'./{model}/u_inf_sin/{case[0]}_{case[1]}_{rf}_alpha_qs.csv')
                write_to_file(phi_qs, f'./{model}/u_inf_sin/{case[0]}_{case[1]}_{rf}_phi_qs.csv')
                print()


def read_data(select, initial, delta, reduced_freq, model):
    if reduced_freq is None:
        return (read_from_file(f'./{model}/{select}_step/{initial}_{delta}_r_list.csv')[0],
                read_from_file(f'./{model}/{select}_step/{initial}_{delta}_t_list.csv')[0],
                read_from_file(f'./{model}/{select}_step/{initial}_{delta}_ctr.csv'),
                read_from_file(f'./{model}/{select}_step/{initial}_{delta}_cqr.csv'),
                read_from_file(f'./{model}/{select}_step/{initial}_{delta}_a.csv'),
                read_from_file(f'./{model}/{select}_step/{initial}_{delta}_alpha.csv'),
                read_from_file(f'./{model}/{select}_step/{initial}_{delta}_phi.csv'),
                read_from_file(f'./{model}/{select}_step/{initial}_{delta}_ctr_qs.csv'),
                read_from_file(f'./{model}/{select}_step/{initial}_{delta}_cqr_qs.csv'),
                read_from_file(f'./{model}/{select}_step/{initial}_{delta}_a_qs.csv'),
                read_from_file(f'./{model}/{select}_step/{initial}_{delta}_alpha_qs.csv'),
                read_from_file(f'./{model}/{select}_step/{initial}_{delta}_phi_qs.csv'))
    else:
        return (read_from_file(f'./{model}/{select}_sin/{initial}_{delta}_{reduced_freq}_r_list.csv')[0],
                read_from_file(f'./{model}/{select}_sin/{initial}_{delta}_{reduced_freq}_t_list.csv')[0],
                read_from_file(f'./{model}/{select}_sin/{initial}_{delta}_{reduced_freq}_ctr.csv'),
                read_from_file(f'./{model}/{select}_sin/{initial}_{delta}_{reduced_freq}_cqr.csv'),
                read_from_file(f'./{model}/{select}_sin/{initial}_{delta}_{reduced_freq}_a.csv'),
                read_from_file(f'./{model}/{select}_sin/{initial}_{delta}_{reduced_freq}_alpha.csv'),
                read_from_file(f'./{model}/{select}_sin/{initial}_{delta}_{reduced_freq}_phi.csv'),
                read_from_file(f'./{model}/{select}_sin/{initial}_{delta}_{reduced_freq}_ctr_qs.csv'),
                read_from_file(f'./{model}/{select}_sin/{initial}_{delta}_{reduced_freq}_cqr_qs.csv'),
                read_from_file(f'./{model}/{select}_sin/{initial}_{delta}_{reduced_freq}_a_qs.csv'),
                read_from_file(f'./{model}/{select}_sin/{initial}_{delta}_{reduced_freq}_alpha_qs.csv'),
                read_from_file(f'./{model}/{select}_sin/{initial}_{delta}_{reduced_freq}_phi_qs.csv'))

def plot_combined_subplot(y_label,ax1,ax2,ax3,ax4,x_lst,y_mat,y_qs_mat,blade_loc_id,blade_loc_tag,color,line,tag,i):
    ax1.plot(x_lst, y_mat[:, blade_loc_id[0]], color=color, linestyle=line, label=tag)
    ax1.set_title(blade_loc_tag[0])
    ax1.set_ylabel(y_label)
    ax1.grid()
    ax2.plot(x_lst, y_mat[:, blade_loc_id[1]], color=color, linestyle=line)
    ax2.set_title(blade_loc_tag[1])
    ax2.set_ylabel(y_label)
    ax2.grid()
    ax3.plot(x_lst, y_mat[:, blade_loc_id[2]], color=color, linestyle=line)
    ax3.set_title(blade_loc_tag[2])
    ax3.set_ylabel(y_label)
    ax3.grid()
    ax4.plot(x_lst, y_mat[:, blade_loc_id[3]], color=color, linestyle=line)
    ax4.set_title(blade_loc_tag[3])
    ax4.set_ylabel(y_label)
    ax4.set_xlabel('Time [s]')
    ax4.grid()
    if not i:
        ax1.plot(x_lst, y_qs_mat[:, blade_loc_id[0]], color=qs_color, linestyle='solid', label='Quasi-steady')
        ax2.plot(x_lst, y_qs_mat[:, blade_loc_id[1]], color=qs_color, linestyle='solid')
        ax3.plot(x_lst, y_qs_mat[:, blade_loc_id[2]], color=qs_color, linestyle='solid')
        ax4.plot(x_lst, y_qs_mat[:, blade_loc_id[3]], color=qs_color, linestyle='solid')
    return

def plot_combined_subplot_red_freq(y_label,ax1,ax2,ax3,ax4,x_lst,y_mat,y_qs_mat,blade_loc_id,blade_loc_tag,color,line,tag,i):
    # Plot once the quasi steady solution with its label
    if not i:
        ax1.plot(x_lst, y_qs_mat[:, blade_loc_id[0]], color=qs_color, linestyle='solid', label='Quasi-steady')
        ax2.plot(x_lst, y_qs_mat[:, blade_loc_id[1]], color=qs_color, linestyle='solid')
        ax3.plot(x_lst, y_qs_mat[:, blade_loc_id[2]], color=qs_color, linestyle='solid')
        ax4.plot(x_lst, y_qs_mat[:, blade_loc_id[3]], color=qs_color, linestyle='solid')
        ax1.grid()
        ax2.grid()
        ax3.grid()
        ax4.grid() 
    # Otherwise just plot the quasi steady solution, without label 
    else:
        ax1.plot(x_lst, y_qs_mat[:, blade_loc_id[0]], color=qs_color, linestyle='solid')
        ax2.plot(x_lst, y_qs_mat[:, blade_loc_id[1]], color=qs_color, linestyle='solid')
        ax3.plot(x_lst, y_qs_mat[:, blade_loc_id[2]], color=qs_color, linestyle='solid')
        ax4.plot(x_lst, y_qs_mat[:, blade_loc_id[3]], color=qs_color, linestyle='solid')
       
    ax1.plot(x_lst, y_mat[:, blade_loc_id[0]], color=color, linestyle=line, label=tag)
    ax1.set_title(blade_loc_tag[0])
    ax1.set_ylabel(y_label)
    ax1.set_xlim(0,628.4)
    ax2.plot(x_lst, y_mat[:, blade_loc_id[1]], color=color, linestyle=line)
    ax2.set_title(blade_loc_tag[1])
    ax2.set_ylabel(y_label)
    ax2.set_xlim(0,628.4)
    ax3.plot(x_lst, y_mat[:, blade_loc_id[2]], color=color, linestyle=line)
    ax3.set_title(blade_loc_tag[2])
    ax3.set_ylabel(y_label)
    ax3.set_xlim(0,628.4)
    ax4.plot(x_lst, y_mat[:, blade_loc_id[3]], color=color, linestyle=line)
    ax4.set_title(blade_loc_tag[3])
    ax4.set_ylabel(y_label)
    ax4.set_xlabel('Time [s]')
    ax4.set_xlim(0,628.4)
    return

def plot_combined_subplot_red_freq_norm(y_label,ax1,ax2,ax3,ax4,x_lst,y_mat,y_qs_mat,blade_loc_id,blade_loc_tag,color,line,tag,i):
    # Plot once the quasi steady solution with its label
    if not i:
        ax1.plot(x_lst, y_qs_mat[:, blade_loc_id[0]], color=qs_color, linestyle='solid', label='Quasi-steady')
        ax2.plot(x_lst, y_qs_mat[:, blade_loc_id[1]], color=qs_color, linestyle='solid')
        ax3.plot(x_lst, y_qs_mat[:, blade_loc_id[2]], color=qs_color, linestyle='solid')
        ax4.plot(x_lst, y_qs_mat[:, blade_loc_id[3]], color=qs_color, linestyle='solid')
        ax1.grid()
        ax2.grid()
        ax3.grid()
        ax4.grid() 
    # Otherwise just plot the quasi steady solution, without label 
    else:
        ax1.plot(x_lst, y_qs_mat[:, blade_loc_id[0]], color=qs_color, linestyle='solid')
        ax2.plot(x_lst, y_qs_mat[:, blade_loc_id[1]], color=qs_color, linestyle='solid')
        ax3.plot(x_lst, y_qs_mat[:, blade_loc_id[2]], color=qs_color, linestyle='solid')
        ax4.plot(x_lst, y_qs_mat[:, blade_loc_id[3]], color=qs_color, linestyle='solid')
       
    ax1.plot(x_lst, y_mat[:, blade_loc_id[0]], color=color, linestyle=line, label=tag)
    ax1.set_title(blade_loc_tag[0])
    ax1.set_ylabel(y_label)
    ax2.plot(x_lst, y_mat[:, blade_loc_id[1]], color=color, linestyle=line)
    ax2.set_title(blade_loc_tag[1])
    ax2.set_ylabel(y_label)
    ax3.plot(x_lst, y_mat[:, blade_loc_id[2]], color=color, linestyle=line)
    ax3.set_title(blade_loc_tag[2])
    ax3.set_ylabel(y_label)
    ax4.plot(x_lst, y_mat[:, blade_loc_id[3]], color=color, linestyle=line)
    ax4.set_title(blade_loc_tag[3])
    ax4.set_ylabel(y_label)
    ax4.set_xlabel('Non-dimensional time: $k \\cdot s$  $\\left(\\omega t \\right)$ [-]')
    return

def plot_combined_subplot_elem(y_label,ax1,ax2,ax3,x_lst,y_mat,y_qs_mat,row_interest,model_tags,color,line,line_label,qs_color,model_i,time_step_counter):
    if model_i == 0 and time_step_counter == 0:
        # Plot the initial state of quasi-steady solution
        ax1.plot(x_lst, y_qs_mat[1, :], color='#069AF3', linestyle='solid', label='Quasi-steady initial')
        ax2.plot(x_lst, y_qs_mat[1, :], color='#069AF3', linestyle='solid')
        ax3.plot(x_lst, y_qs_mat[1, :], color='#069AF3', linestyle='solid')
        # Plot the final state of quasi-steady solution
        ax1.plot(x_lst, y_qs_mat[-1, :], color='#F97306', linestyle='solid', label='Quasi-steady final')
        ax2.plot(x_lst, y_qs_mat[-1, :], color='#F97306', linestyle='solid')
        ax3.plot(x_lst, y_qs_mat[-1, :], color='#F97306', linestyle='solid')
        ax1.grid()
        ax2.grid()
        ax3.grid()
    if model_i == 0:
        ax1.plot(x_lst, y_mat[row_interest, :], color=color, linestyle=line, label=line_label)
        ax1.set_title(model_tags[model_i])
        ax1.set_ylabel(y_label)
        ax1.set_xlabel('Blade radial position [m]')
    elif model_i == 1:
        ax2.plot(x_lst, y_mat[row_interest, :], color=color, linestyle=line)
        ax2.set_title(model_tags[model_i])
        ax2.set_xlabel('Blade radial position [m]')
    else:
        ax3.plot(x_lst, y_mat[row_interest, :], color=color, linestyle=line)
        ax3.set_title(model_tags[model_i])
        ax3.set_xlabel('Blade radial position [m]')
    return


def plot_save_figure(fig_tag,case_tag,case_ID,response_tag,freq_red_tag,folder_name):
    fig_tag.tight_layout()
    if freq_red_tag == 0.0:
        fig_tag.subplots_adjust(bottom=0.15)
        fig_tag.legend(frameon=False, loc='upper center', bbox_to_anchor=(0.5, 0.07), ncol=4)
        fig_name = case_tag + '_' + str(case_ID) + '_' + response_tag + '_time.pdf'
    else:
        fig_tag.subplots_adjust(bottom=0.28)
        fig_tag.legend(frameon=False, loc='upper center', bbox_to_anchor=(0.5, 0.14), ncol=4)
        fig_name = case_tag + '_' + str(case_ID) + '_' + response_tag + '_k' + str(freq_red_tag) + '_time.pdf'
    fig_tag.savefig(folder_name + '\\' + fig_name)
    return

def plot_save_figure_elem(fig_tag,case_tag,case_ID,response_tag,folder_name):
    fig_tag.tight_layout()
    fig_tag.subplots_adjust(bottom=0.2)
    fig_tag.legend(frameon=False, loc='upper center', bbox_to_anchor=(0.5, 0.1), ncol=4)
    fig_name = case_tag + '_' + str(case_ID) + '_' + response_tag + '_blade_elem.pdf'
    fig_tag.savefig(folder_name + '\\' + fig_name)
    return

if __name__ == '__main__':
    # Create the turbine with 25 blade elements
    turbine = Turbine(25)
    
#    # User inputs: Uncomment the following line to manually select the case and condition to be plotted
#    # Select the case to be plotted; Either: A1, A2, B1, B2
#    case_tag = 'B2'
#    
#    # Select the condition number to be plotted (i.e. row number of interest in the table of the assignment);
#    #   For A1 : 1-4
#    #   For A2 : 1-3
#    #   For B1 : 1-4
#    #   For B2 : 1-3
#    case_ID = 3
    
    # Define the range of case tags considered
    case_tag_range = ('A1','A2','B1','B2')
    
    # Define the range of conditions considered under each case (4 conditions for A1 and B1, and 3 conditions under A2 and B2)
    case_cond_range_A1B1 = (1,2,3,4)
    case_cond_range_A2B2 = (1,2,3)
    
    # Define blade locations of interest and plotting styles
    blade_loc_id = (0, 8, -2, -1)
    blade_loc_tag = ('0.2 R','0.5 R','0.9 R','1.0 R')
    blade_loc_line = ('solid', 'dotted', 'dashed', 'dashdot')
    
    # Define the color range (one per model)
    model_colors = ('#15B01A', '#EF4026', '#F97306')
    model_marker = ('o','s','p')
    model_line = ('dashed', 'dotted', 'dashdot')
    model_tag = ('Pitt-Peters', 'Larsen-Madsen', 'Oye')
    qs_color = '#069AF3'
    
    # Close and clear all plots
    plt.close('all')
    
    for case_tag_i, case_tag in enumerate(case_tag_range):
        # Define the range of redced frequency for sinusodal perturbations
        if case_tag == 'A2' or case_tag == 'B2':
            freq_red_range = (0.05,0.10,0.15,0.20,0.25,0.30)    # Reduced frequency range required from assignment
            case_ID_range = case_cond_range_A2B2
        else:
            freq_red_range = [0.00]      # Dummy variable, as long as it is one value, step change responses will only be plotted once
            case_ID_range = case_cond_range_A1B1

        for case_ID_i, case_ID in enumerate(case_ID_range):            
            # Plotting the five responses over time for the three models (and the 6 reduced frequencies for case A2 and B2)
            print('Plotting responses over time.')
            for freq_red_index, freq_red in enumerate(freq_red_range): 
                print('k = ',freq_red)               
                # Initialise the plots
                fig_a, (ax_a1,ax_a2,ax_a3,ax_a4) = plt.subplots(4, 1,sharex=True, figsize=(9, 5))           # a: Induction factor
                fig_ct, (ax_ct1,ax_ct2,ax_ct3,ax_ct4) = plt.subplots(4, 1,sharex=True, figsize=(9, 5))      # ct: Thrust coefficient
                fig_cq, (ax_cq1,ax_cq2,ax_cq3,ax_cq4) = plt.subplots(4, 1,sharex=True, figsize=(9, 5))      # cq: Torque coefficient
                fig_aoa, (ax_aoa1,ax_aoa2,ax_aoa3,ax_aoa4) = plt.subplots(4, 1,sharex=True, figsize=(9, 5)) # aoa: Angle of attack (alpha)
                fig_phi, (ax_phi1,ax_phi2,ax_phi3,ax_phi4) = plt.subplots(4, 1,sharex=True, figsize=(9, 5)) # phi: Inflow angle
                
                # Loop over each model
                for i, model in enumerate(('pp', 'lm', 'oye')):
                    print(model)
                    if case_tag == 'A1':
                        r_list, t_list, ctr, cqr, a, alpha, phi, ctr_qs, cqr_qs, a_qs, alpha_qs, phi_qs = read_data('ct', *ct_steps[case_ID-1], None, model=model) # NB: Use case_ID-1 to comply with Python indexing convention
                    elif case_tag == 'A2':
                        r_list, t_list, ctr, cqr, a, alpha, phi, ctr_qs, cqr_qs, a_qs, alpha_qs, phi_qs = read_data('ct', *ct_sins[case_ID-1], freq_red, model=model)
                    elif case_tag == 'B1':
                        r_list, t_list, ctr, cqr, a, alpha, phi, ctr_qs, cqr_qs, a_qs, alpha_qs, phi_qs = read_data('u_inf', *u_inf_steps[case_ID-1], None, model=model)
                    elif case_tag == 'B2':
                        r_list, t_list, ctr, cqr, a, alpha, phi, ctr_qs, cqr_qs, a_qs, alpha_qs, phi_qs = read_data('u_inf', *u_inf_sins[case_ID-1], freq_red, model=model)
                    else:
                        print('Warning: Invalid case tag enterred.')
                        
                    # OLD CODE; Used to run the simulations
                    # r_list, t_list, ctr, cqr, a, alpha, phi, ctr_qs, cqr_qs, a_qs, alpha_qs, phi_qs = turbine.ct_func(.5, .4, None, 10, 10, model=model)
                    # r_list, t_list, ctr, cqr, a, alpha, phi, ctr_qs, cqr_qs, a_qs, alpha_qs, phi_qs = turbine.ct_func(.5, .5, .3, 10, 10, model=model)
                    # r_list, t_list, ctr, cqr, a, alpha, phi, ctr_qs, cqr_qs, a_qs, alpha_qs, phi_qs = turbine.u_inf_func(1., .5, None, 10, 10, model=model)
                    # r_list, t_list, ctr, cqr, a, alpha, phi, ctr_qs, cqr_qs, a_qs, alpha_qs, phi_qs = turbine.u_inf_func(1., .5, .3, 10, 10, model=model)
            
                    # Assemble the plots
                    plot_combined_subplot('a [-]',ax_a1,ax_a2,ax_a3,ax_a4,t_list,a,a_qs,blade_loc_id,blade_loc_tag,model_colors[i],model_line[i],model_tag[i],i)
                    plot_combined_subplot('$C_t$ [-]',ax_ct1,ax_ct2,ax_ct3,ax_ct4,t_list,ctr,ctr_qs,blade_loc_id,blade_loc_tag,model_colors[i],model_line[i],model_tag[i],i)
                    plot_combined_subplot('$C_q$ [-]',ax_cq1,ax_cq2,ax_cq3,ax_cq4,t_list,cqr,cqr_qs,blade_loc_id,blade_loc_tag,model_colors[i],model_line[i],model_tag[i],i)
                    plot_combined_subplot('$\\alpha$ [deg]',ax_aoa1,ax_aoa2,ax_aoa3,ax_aoa4,t_list,alpha,alpha_qs,blade_loc_id,blade_loc_tag,model_colors[i],model_line[i],model_tag[i],i)
                    plot_combined_subplot('$\\phi$ [deg]',ax_phi1,ax_phi2,ax_phi3,ax_phi4,t_list,phi,phi_qs,blade_loc_id,blade_loc_tag,model_colors[i],model_line[i],model_tag[i],i)
            
                    
                # Save the plots to .pdf
                plot_save_figure(fig_a,case_tag,case_ID,'a',freq_red,'Figures')
                plot_save_figure(fig_ct,case_tag,case_ID,'ct',freq_red,'Figures')
                plot_save_figure(fig_cq,case_tag,case_ID,'cq',freq_red,'Figures')
                plot_save_figure(fig_aoa,case_tag,case_ID,'aoa',freq_red,'Figures')
                plot_save_figure(fig_phi,case_tag,case_ID,'phi',freq_red,'Figures')
             
            # Plot each model on separate plot; plot range of reduced frequencies
            if case_tag == 'A2' or case_tag == 'B2':    # Loop over each model
                print('Plotting responses over time over range of reduced frequencies.')
                for i, model in enumerate(('pp', 'lm', 'oye')):
                    print(model)
                    # Initialise the plots
                    fig_a_k, (ax_ak1,ax_ak2,ax_ak3,ax_ak4) = plt.subplots(4, 1,sharex=True, figsize=(9, 5))           # a: Induction factor
                    fig_ct_k, (ax_ctk1,ax_ctk2,ax_ctk3,ax_ctk4) = plt.subplots(4, 1,sharex=True, figsize=(9, 5))      # ct: Thrust coefficient
                    fig_cq_k, (ax_cqk1,ax_cqk2,ax_cqk3,ax_cqk4) = plt.subplots(4, 1,sharex=True, figsize=(9, 5))      # cq: Torque coefficient
                    fig_aoa_k, (ax_aoak1,ax_aoak2,ax_aoak3,ax_aoak4) = plt.subplots(4, 1,sharex=True, figsize=(9, 5)) # aoa: Angle of attack (alpha)
                    fig_phi_k, (ax_phik1,ax_phik2,ax_phik3,ax_phik4) = plt.subplots(4, 1,sharex=True, figsize=(9, 5)) # phi: Inflow angle
                    
                    for freq_red_index, freq_red in enumerate(freq_red_range):  # Loop over each frequency
                        print(freq_red)
                        if case_tag == 'A1':
                            r_list, t_list, ctr, cqr, a, alpha, phi, ctr_qs, cqr_qs, a_qs, alpha_qs, phi_qs = read_data('ct', *ct_steps[case_ID-1], None, model=model) # NB: Use case_ID-1 to comply with Python indexing convention
                        elif case_tag == 'A2':
                            r_list, t_list, ctr, cqr, a, alpha, phi, ctr_qs, cqr_qs, a_qs, alpha_qs, phi_qs = read_data('ct', *ct_sins[case_ID-1], freq_red, model=model)
                        elif case_tag == 'B1':
                            r_list, t_list, ctr, cqr, a, alpha, phi, ctr_qs, cqr_qs, a_qs, alpha_qs, phi_qs = read_data('u_inf', *u_inf_steps[case_ID-1], None, model=model)
                        elif case_tag == 'B2':
                            r_list, t_list, ctr, cqr, a, alpha, phi, ctr_qs, cqr_qs, a_qs, alpha_qs, phi_qs = read_data('u_inf', *u_inf_sins[case_ID-1], freq_red, model=model)
                        else:
                            print('Warning: Invalid case tag enterred.')
                        
                        # Assemble the plots
                        freq_red_grayscale = str(1 - (freq_red_index+1)/len(freq_red_range))    # Plot the different reduced frequency lines with a shade of grey [0 = Black; 1 = White]
                        plot_combined_subplot_red_freq('a [-]',ax_ak1,ax_ak2,ax_ak3,ax_ak4,t_list,a,a_qs,blade_loc_id,blade_loc_tag,freq_red_grayscale,'--','k = '+str(freq_red),freq_red_index)
                        plot_combined_subplot_red_freq('$C_t$ [-]',ax_ctk1,ax_ctk2,ax_ctk3,ax_ctk4,t_list,ctr,ctr_qs,blade_loc_id,blade_loc_tag,freq_red_grayscale,'--','k = '+str(freq_red),freq_red_index)
                        plot_combined_subplot_red_freq('$C_q$ [-]',ax_cqk1,ax_cqk2,ax_cqk3,ax_cqk4,t_list,cqr,cqr_qs,blade_loc_id,blade_loc_tag,freq_red_grayscale,'--','k = '+str(freq_red),freq_red_index)
                        plot_combined_subplot_red_freq('$\\alpha$ [deg]',ax_aoak1,ax_aoak2,ax_aoak3,ax_aoak4,t_list,alpha,alpha_qs,blade_loc_id,blade_loc_tag,freq_red_grayscale,'--','k = '+str(freq_red),freq_red_index)
                        plot_combined_subplot_red_freq('$\\phi$ [deg]',ax_phik1,ax_phik2,ax_phik3,ax_phik4,t_list,phi,phi_qs,blade_loc_id,blade_loc_tag,freq_red_grayscale,'--','k = '+str(freq_red),freq_red_index)
                
                        
                    # Save the plots to .pdf
                    plot_save_figure(fig_a_k,case_tag,case_ID,'a','_'+str(model),'Figures')
                    plot_save_figure(fig_ct_k,case_tag,case_ID,'ct','_'+str(model),'Figures')
                    plot_save_figure(fig_cq_k,case_tag,case_ID,'cq','_'+str(model),'Figures')
                    plot_save_figure(fig_aoa_k,case_tag,case_ID,'aoa','_'+str(model),'Figures')
                    plot_save_figure(fig_phi_k,case_tag,case_ID,'phi','_'+str(model),'Figures')
                    
            # Plot each model on separate plot; plot range of reduced frequencies normalised
            if case_tag == 'A2' or case_tag == 'B2':    # Loop over each model
                print('Plotting responses over time over range of reduced frequencies normalised.')
                for i, model in enumerate(('pp', 'lm', 'oye')):
                    print(model)
                    # Initialise the plots
                    fig_a_k, (ax_ak1,ax_ak2,ax_ak3,ax_ak4) = plt.subplots(4, 1,sharex=True, figsize=(9, 5))           # a: Induction factor
                    fig_ct_k, (ax_ctk1,ax_ctk2,ax_ctk3,ax_ctk4) = plt.subplots(4, 1,sharex=True, figsize=(9, 5))      # ct: Thrust coefficient
                    fig_cq_k, (ax_cqk1,ax_cqk2,ax_cqk3,ax_cqk4) = plt.subplots(4, 1,sharex=True, figsize=(9, 5))      # cq: Torque coefficient
                    fig_aoa_k, (ax_aoak1,ax_aoak2,ax_aoak3,ax_aoak4) = plt.subplots(4, 1,sharex=True, figsize=(9, 5)) # aoa: Angle of attack (alpha)
                    fig_phi_k, (ax_phik1,ax_phik2,ax_phik3,ax_phik4) = plt.subplots(4, 1,sharex=True, figsize=(9, 5)) # phi: Inflow angle
                    
                    for freq_red_index, freq_red in enumerate(freq_red_range):  # Loop over each frequency
                        print(freq_red)
                        if case_tag == 'A1':
                            r_list, t_list, ctr, cqr, a, alpha, phi, ctr_qs, cqr_qs, a_qs, alpha_qs, phi_qs = read_data('ct', *ct_steps[case_ID-1], None, model=model) # NB: Use case_ID-1 to comply with Python indexing convention
                        elif case_tag == 'A2':
                            r_list, t_list, ctr, cqr, a, alpha, phi, ctr_qs, cqr_qs, a_qs, alpha_qs, phi_qs = read_data('ct', *ct_sins[case_ID-1], freq_red, model=model)
                        elif case_tag == 'B1':
                            r_list, t_list, ctr, cqr, a, alpha, phi, ctr_qs, cqr_qs, a_qs, alpha_qs, phi_qs = read_data('u_inf', *u_inf_steps[case_ID-1], None, model=model)
                        elif case_tag == 'B2':
                            r_list, t_list, ctr, cqr, a, alpha, phi, ctr_qs, cqr_qs, a_qs, alpha_qs, phi_qs = read_data('u_inf', *u_inf_sins[case_ID-1], freq_red, model=model)
                        else:
                            print('Warning: Invalid case tag enterred.')
                        
                        # Assemble the plots
                        V0 = 10                             # [m/s] : Wind speed
                        R = 50                              # [m] : Blade length
                        norm_time = t_list*V0/R*freq_red    # [-] : Normalised time scale
                        freq_red_grayscale = str(1 - (freq_red_index+1)/len(freq_red_range))    # Plot the different reduced frequency lines with a shade of grey [0 = Black; 1 = White]
                        plot_combined_subplot_red_freq_norm('a [-]',ax_ak1,ax_ak2,ax_ak3,ax_ak4,norm_time,a,a_qs,blade_loc_id,blade_loc_tag,freq_red_grayscale,'--','k = '+str(freq_red),freq_red_index)
                        plot_combined_subplot_red_freq_norm('$C_t$ [-]',ax_ctk1,ax_ctk2,ax_ctk3,ax_ctk4,norm_time,ctr,ctr_qs,blade_loc_id,blade_loc_tag,freq_red_grayscale,'--','k = '+str(freq_red),freq_red_index)
                        plot_combined_subplot_red_freq_norm('$C_q$ [-]',ax_cqk1,ax_cqk2,ax_cqk3,ax_cqk4,norm_time,cqr,cqr_qs,blade_loc_id,blade_loc_tag,freq_red_grayscale,'--','k = '+str(freq_red),freq_red_index)
                        plot_combined_subplot_red_freq_norm('$\\alpha$ [deg]',ax_aoak1,ax_aoak2,ax_aoak3,ax_aoak4,norm_time,alpha,alpha_qs,blade_loc_id,blade_loc_tag,freq_red_grayscale,'--','k = '+str(freq_red),freq_red_index)
                        plot_combined_subplot_red_freq_norm('$\\phi$ [deg]',ax_phik1,ax_phik2,ax_phik3,ax_phik4,norm_time,phi,phi_qs,blade_loc_id,blade_loc_tag,freq_red_grayscale,'--','k = '+str(freq_red),freq_red_index)
                
                
                    # Save the plots to .pdf
                    plot_save_figure(fig_a_k,case_tag,case_ID,'a','_norm_'+str(model),'Figures')
                    plot_save_figure(fig_ct_k,case_tag,case_ID,'ct','_norm_'+str(model),'Figures')
                    plot_save_figure(fig_cq_k,case_tag,case_ID,'cq','_norm_'+str(model),'Figures')
                    plot_save_figure(fig_aoa_k,case_tag,case_ID,'aoa','_norm_'+str(model),'Figures')
                    plot_save_figure(fig_phi_k,case_tag,case_ID,'phi','_norm_'+str(model),'Figures')
            
            # Plotting responses over blade radial position        
            if case_tag == 'A1' or case_tag == 'B1':
                print('Plotting responses over radial positions.')
                # Initialise the plots
                fig_a_elem, (ax_a1_elem,ax_a2_elem,ax_a3_elem) = plt.subplots(1, 3, sharey=True, figsize=(9, 5))            # a: Induction factor
                fig_ct_elem, (ax_ct1_elem,ax_ct2_elem,ax_ct3_elem) = plt.subplots(1, 3, sharey=True, figsize=(9, 5))        # ct: Thrust coefficient
                fig_cq_elem, (ax_cq1_elem,ax_cq2_elem,ax_cq3_elem) = plt.subplots(1, 3,sharey=True, figsize=(9, 5))         # cq: Torque coefficient
                fig_aoa_elem, (ax_aoa1_elem,ax_aoa2_elem,ax_aoa3_elem) = plt.subplots(1, 3,sharey=True, figsize=(9, 5))     # aoa: Angle of attack (alpha)
                fig_phi_elem, (ax_phi1_elem,ax_phi2_elem,ax_phi3_elem) = plt.subplots(1, 3,sharey=True, figsize=(9, 5))     # phi: Inflow angle
                
                
                # Loop over each model
                for model_i, model in enumerate(('pp', 'lm', 'oye')):
                    print(model)
                    if case_tag == 'A1':
                        r_list, t_list, ctr, cqr, a, alpha, phi, ctr_qs, cqr_qs, a_qs, alpha_qs, phi_qs = read_data('ct', *ct_steps[case_ID-1], None, model=model) # NB: Use case_ID-1 to comply with Python indexing convention
                    elif case_tag == 'B1':
                        r_list, t_list, ctr, cqr, a, alpha, phi, ctr_qs, cqr_qs, a_qs, alpha_qs, phi_qs = read_data('u_inf', *u_inf_steps[case_ID-1], None, model=model)
                    else:
                        print('Warning: Invalid case tag enterred.')
                    
                    # Initialise the counter of time steps performed
                    time_step_counter = 0
                    
                    # Loop over all time steps of interest
                    for row_of_a in range(a.shape[0]):
                        time_sampling = 10  # Define the time step for which to retrieve the responses
                        if t_list[row_of_a]%time_sampling == 0: 
                            # Assemble the plots
                            time_step_grayscale = str((time_step_counter)/6)    # Divide by 6 to have a grayscale with depth, need to update this value if more time steps are considered
                            plot_combined_subplot_elem('a [-]',ax_a1_elem,ax_a2_elem,ax_a3_elem,r_list,a,a_qs,row_of_a,model_tag,time_step_grayscale,'--','t [s] = '+str(t_list[row_of_a]),qs_color,model_i,time_step_counter)
                            plot_combined_subplot_elem('$C_t$ [-]',ax_ct1_elem,ax_ct2_elem,ax_ct3_elem,r_list,ctr,ctr_qs,row_of_a,model_tag,time_step_grayscale,'--','t [s] = '+str(t_list[row_of_a]),qs_color,model_i,time_step_counter)
                            plot_combined_subplot_elem('$C_q$ [-]',ax_cq1_elem,ax_cq2_elem,ax_cq3_elem,r_list,cqr,cqr_qs,row_of_a,model_tag,time_step_grayscale,'--','t [s] = '+str(t_list[row_of_a]),qs_color,model_i,time_step_counter)
                            plot_combined_subplot_elem('$\\alpha$ [deg]',ax_aoa1_elem,ax_aoa2_elem,ax_aoa3_elem,r_list,alpha,alpha_qs,row_of_a,model_tag,time_step_grayscale,'--','t [s] = '+str(t_list[row_of_a]),qs_color,model_i,time_step_counter)
                            plot_combined_subplot_elem('$\\phi$ [deg]',ax_phi1_elem,ax_phi2_elem,ax_phi3_elem,r_list,phi,phi_qs,row_of_a,model_tag,time_step_grayscale,'--','t [s] = '+str(t_list[row_of_a]),qs_color,model_i,time_step_counter)
                            
                            # Increment the counter of time steps performed
                            time_step_counter += 1
                            
                # Save the plots to .pdf
                plot_save_figure_elem(fig_a_elem,case_tag,case_ID,'a','Figures')
                plot_save_figure_elem(fig_ct_elem,case_tag,case_ID,'ct','Figures')
                plot_save_figure_elem(fig_cq_elem,case_tag,case_ID,'cq','Figures')
                plot_save_figure_elem(fig_aoa_elem,case_tag,case_ID,'aoa','Figures')
                plot_save_figure_elem(fig_phi_elem,case_tag,case_ID,'phi','Figures')
    
    plt.show()
