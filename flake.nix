{
  description = "Morning briefing system - Oura-triggered daily briefing";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs = { self, nixpkgs }:
  let
    system = "x86_64-linux";
    pkgs = import nixpkgs { inherit system; };
    py = pkgs.python3.withPackages (ps: with ps; [
      requests
    ]);
  in
  {
    devShells.${system}.default = pkgs.mkShell {
      packages = [ py ];

      shellHook = ''
        echo "Morning briefing dev environment"
        echo "Python: $(python --version)"
      '';
    };
  };
}
