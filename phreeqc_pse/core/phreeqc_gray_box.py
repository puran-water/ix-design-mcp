"""
PHREEQC GrayBox Model
Following the Reaktoro-PSE pattern for external equilibrium solver integration
"""

import numpy as np
from scipy.sparse import coo_matrix
from pyomo.contrib.pynumero.interfaces.external_grey_box import ExternalGreyBoxModel
import logging

logger = logging.getLogger(__name__)


class PhreeqcGrayBox(ExternalGreyBoxModel):
    """
    GrayBox model for PHREEQC integration with Pyomo/IDAES
    
    This class wraps PHREEQC calculations in a format that Pyomo's
    optimization framework can work with, handling:
    - Input/output variable mapping
    - Jacobian calculations
    - Mass balance enforcement
    """
    
    def configure(self, phreeqc_solver, inputs, outputs, input_specs=None):
        """
        Configure the GrayBox model
        
        Args:
            phreeqc_solver: PhreeqcSolver instance that runs PHREEQC
            inputs: List of input variable names (e.g., ['Ca_in', 'Mg_in', ...])
            outputs: List of output variable names (e.g., ['Ca_out', 'Mg_out', ...])
            input_specs: Optional dict of input specifications
        """
        self.phreeqc_solver = phreeqc_solver
        self.inputs = inputs
        self.outputs = outputs
        self.input_specs = input_specs or {}
        
        # Initialize arrays
        self._input_values = np.zeros(len(inputs))
        self._output_values = np.zeros(len(outputs))
        self._jacobian = None
        
        # Track solver iterations
        self.iteration_count = 0
        self.last_inputs = None
        
        logger.info(f"PhreeqcGrayBox configured with {len(inputs)} inputs, {len(outputs)} outputs")
    
    def input_names(self):
        """Return list of input names (required by GrayBox interface)"""
        return self.inputs
    
    def output_names(self):
        """Return list of output names"""
        return self.outputs
    
    def set_input_values(self, input_values):
        """Set input values from Pyomo (required by GrayBox interface)"""
        self._input_values = np.array(input_values)
    
    def evaluate_outputs(self):
        """
        Evaluate PHREEQC model with current inputs
        
        Returns:
            numpy.array: Output values
        """
        # Check if inputs have changed
        if self.last_inputs is not None and np.allclose(self._input_values, self.last_inputs):
            # Return cached results
            return self._output_values
        
        # Convert inputs to dict
        input_dict = dict(zip(self.inputs, self._input_values))
        
        # Run PHREEQC
        try:
            results = self.phreeqc_solver.solve(input_dict)
            
            # Extract outputs
            self._output_values = np.array([
                results.get(output, 0.0) for output in self.outputs
            ])
            
            # Cache Jacobian if calculated
            if hasattr(results, 'jacobian'):
                self._jacobian = results.jacobian
            
            # Update tracking
            self.last_inputs = self._input_values.copy()
            self.iteration_count += 1
            
        except Exception as e:
            logger.error(f"PHREEQC evaluation failed: {e}")
            # Return last valid outputs or zeros
            if self._output_values is None:
                self._output_values = np.zeros(len(self.outputs))
        
        return self._output_values
    
    def evaluate_jacobian_outputs(self):
        """
        Evaluate Jacobian of outputs with respect to inputs
        
        Returns:
            scipy.sparse.coo_matrix: Sparse Jacobian matrix
        """
        # First evaluate outputs to ensure we have current results
        self.evaluate_outputs()
        
        if self._jacobian is not None:
            # Use analytical Jacobian if available
            jac = self._jacobian
        else:
            # Calculate numerical Jacobian
            jac = self._calculate_numerical_jacobian()
        
        # Convert to sparse format
        n_out = len(self.outputs)
        n_in = len(self.inputs)
        
        # Flatten for COO format
        row_indices = []
        col_indices = []
        values = []
        
        for i in range(n_out):
            for j in range(n_in):
                if abs(jac[i, j]) > 1e-12:  # Only include non-zero elements
                    row_indices.append(i)
                    col_indices.append(j)
                    values.append(jac[i, j])
        
        return coo_matrix((values, (row_indices, col_indices)), shape=(n_out, n_in))
    
    def _calculate_numerical_jacobian(self, step_size=1e-6):
        """
        Calculate Jacobian using finite differences
        
        Args:
            step_size: Step size for finite difference
            
        Returns:
            numpy.array: Jacobian matrix
        """
        n_out = len(self.outputs)
        n_in = len(self.inputs)
        jac = np.zeros((n_out, n_in))
        
        # Save current outputs
        base_outputs = self._output_values.copy()
        base_inputs = self._input_values.copy()
        
        # Calculate derivatives
        for j in range(n_in):
            # Perturb input j
            perturbed_inputs = base_inputs.copy()
            perturbed_inputs[j] += step_size
            
            # Evaluate with perturbed input
            self._input_values = perturbed_inputs
            perturbed_outputs = self.evaluate_outputs()
            
            # Calculate derivative
            jac[:, j] = (perturbed_outputs - base_outputs) / step_size
        
        # Restore original inputs
        self._input_values = base_inputs
        
        return jac
    
    def finalize_block_construction(self, pyomo_block):
        """
        Initialize variables on the Pyomo block
        
        Args:
            pyomo_block: Pyomo block containing the GrayBox model
        """
        # Set reasonable initial values
        if hasattr(pyomo_block, 'inputs'):
            for i, var_name in enumerate(self.inputs):
                if var_name in pyomo_block.inputs:
                    # Set based on input type
                    if 'flow' in var_name.lower():
                        pyomo_block.inputs[var_name].value = 0.001  # kg/s
                    elif 'temp' in var_name.lower():
                        pyomo_block.inputs[var_name].value = 298.15  # K
                    elif 'pressure' in var_name.lower():
                        pyomo_block.inputs[var_name].value = 101325  # Pa
                    else:
                        pyomo_block.inputs[var_name].value = 0.0001  # Default
                    
                    # Set bounds
                    pyomo_block.inputs[var_name].setlb(0)
        
        if hasattr(pyomo_block, 'outputs'):
            for i, var_name in enumerate(self.outputs):
                if var_name in pyomo_block.outputs:
                    pyomo_block.outputs[var_name].value = 0.0001
                    pyomo_block.outputs[var_name].setlb(0)
    
    def get_output_constraint_scaling_factors(self):
        """
        Provide scaling factors for outputs
        
        Returns:
            numpy.array: Scaling factors
        """
        # Default scaling based on output names
        scaling = np.ones(len(self.outputs))
        
        for i, output in enumerate(self.outputs):
            if 'flow' in output.lower():
                scaling[i] = 1000  # kg/s to g/s
            elif 'conc' in output.lower():
                scaling[i] = 1000  # kg/m3 to g/m3
            elif 'removal' in output.lower():
                scaling[i] = 100   # Fraction to percentage
        
        return scaling