cmake_minimum_required(VERSION 3.18)
project(nexa_geometry LANGUAGES CXX)
add_library(nexa_geometry SHARED geometry.cpp)
target_compile_features(nexa_geometry PRIVATE cxx_std_17)
