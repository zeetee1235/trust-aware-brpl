{
  description = "TA-BRPL (Trust Aware Backpressure RPL) Development Environment";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
      in
      {
        devShells.default = pkgs.mkShell {
          name = "ta-brpl-env";

          buildInputs = with pkgs; [
            # Core build tools
            gcc
            gnumake
            git
            
            # Java for Cooja
            openjdk17
            
            # Python with common packages
            python3
            python3Packages.pip
            python3Packages.virtualenv
            python3Packages.numpy
            python3Packages.pandas
            python3Packages.matplotlib
            
            # R with packages for analysis
            R
            rPackages.ggplot2
            rPackages.dplyr
            rPackages.tidyr
            rPackages.readr
            rPackages.scales
            rPackages.gridExtra
            
            # Additional utilities
            which
            coreutils
            bash
          ];

          shellHook = ''
            echo "🔧 TA-BRPL Development Environment"
            echo "=================================="
            echo "Java version: $(java -version 2>&1 | head -n 1)"
            echo "Python version: $(python3 --version)"
            echo "R version: $(R --version | head -n 1)"
            echo "GCC version: $(gcc --version | head -n 1)"
            echo ""
            
            # Initialize submodule if needed
            if [ ! -f contiki-ng-brpl/.git ]; then
              echo "Contiki-NG submodule not initialized"
              echo "Run: git submodule update --init --recursive"
              echo ""
            fi
            
            # Set Java options for Cooja
            export JAVA_OPTS="-Xmx4G -Xms2G"
            
            # Set Cooja path (adjust if needed)
            export COOJA_PATH="''${COOJA_PATH:-/home/dev/contiki-ng}"
            
            # Set Contiki path to submodule
            export CONTIKI="$PWD/contiki-ng-brpl"
            
            echo "Environment ready!"
            echo ""
            echo "Quick commands:"
            echo "  - Initialize submodule: git submodule update --init --recursive"
            echo "  - Build motes: make"
            echo "  - Run quick test: QUICK_PREVIEW=1 ./scripts/run_experiments.sh"
            echo "  - Single test: TOPOLOGY=configs/topologies/GRID_L.csc ./scripts/single_test.sh"
            echo ""
          '';
        };
      }
    );
}
